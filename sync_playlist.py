import os
import shutil
import json
import time
import urllib.request
import urllib.parse
import urllib.error
from plexapi.server import PlexServer

# Tentar carregar via python-dotenv se disponível; caso contrário, carregar manualmente do .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # Fallback leve caso python-dotenv não esteja instalado
    env_file = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_file):
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, val = line.split('=', 1)
                    os.environ.setdefault(key.strip(), val.strip().strip("'\""))

# --- CONFIGURAÇÕES CARREGADAS DO .ENV ---
PLEX_URL = os.getenv('PLEX_URL', 'http://127.0.0.1:32400').rstrip('/')
PLEX_TOKEN = os.getenv('PLEX_TOKEN', '')

# Lista de playlists a sincronizar (separadas por vírgula no .env)
_raw_playlists = os.getenv('PLAYLISTS_TO_SYNC', '❤️ Tracks, Carro, Populares')
PLAYLISTS_TO_SYNC = [name.strip() for name in _raw_playlists.split(',') if name.strip()]

# Pasta raiz e subdiretórios
BASE_TARGET_DIR = os.getenv('BASE_TARGET_DIR', '/mnt/usb/musica_carro')
MEDIA_SUBDIR = os.getenv('MEDIA_SUBDIR', 'Media')
PLAYLISTS_SUBDIR = os.getenv('PLAYLISTS_SUBDIR', 'Playlists')

# Definições de letras (.lrc) via LRCLIB (o motor usado pelo LRCGET)
SYNC_LYRICS = os.getenv('SYNC_LYRICS', 'true').strip().lower() in ('1', 'true', 'yes', 'on')
FALLBACK_PLAIN_LYRICS = os.getenv('FALLBACK_PLAIN_LYRICS', 'false').strip().lower() in ('1', 'true', 'yes', 'on')
# ----------------------------------------

def safe_copy_file(src, dst):
    """
    Copia o ficheiro usando um temporário (.part) e shutil.copyfile.
    Evita [Errno 1] Operation not permitted em discos FAT32/exFAT/NTFS ou partilhas SMB,
    pois o copyfile copia apenas o fluxo de bytes sem forçar permissões POSIX (chmod).
    """
    temp_dst = dst + ".part"
    try:
        shutil.copyfile(src, temp_dst)
        
        # Tenta sincronizar timestamps (data/hora) se o disco suportar;
        # se falhar (comum em SMB/FAT/exFAT), ignora o erro de permissão.
        try:
            shutil.copystat(src, temp_dst)
        except (PermissionError, OSError):
            pass
            
        os.replace(temp_dst, dst)
    except Exception:
        if os.path.exists(temp_dst):
            try:
                os.remove(temp_dst)
            except OSError:
                pass
        raise

def fetch_lrclib_lyrics(track_name, artist_name, album_name=None, duration_sec=None, allow_plain=False):
    """
    Procura e descarrega a letra sincronizada (.lrc) a partir da API da LRCLIB
    (o mesmo serviço oficial utilizado pela aplicação LRCGET).
    """
    headers = {
        'User-Agent': 'LRCGET/0.8.0 (https://github.com/tranxuanthang/lrcget)'
    }

    def _request_json(url):
        # Trata sobrecargas transitórias (HTTP 503 / 429) respeitando o retry-after
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    return json.loads(resp.read().decode('utf-8'))
            except urllib.error.HTTPError as e:
                if e.code in (429, 503):
                    retry_after = int(e.headers.get('retry-after', '1'))
                    time.sleep(retry_after + 0.5)
                    continue
                if e.code == 404:
                    return None
                return None
            except Exception:
                time.sleep(1)
        return None

    # 1. Tentativa exata via /api/get
    params = {'track_name': track_name, 'artist_name': artist_name}
    if album_name:
        params['album_name'] = album_name
    if duration_sec:
        params['duration'] = duration_sec

    data = _request_json('https://lrclib.net/api/get?' + urllib.parse.urlencode(params))
    if data:
        if data.get('syncedLyrics'):
            return data['syncedLyrics'], 'sincronizada'
        if allow_plain and data.get('plainLyrics'):
            return data['plainLyrics'], 'texto simples'

    # 2. Tentativa aproximada via /api/search (caso a duração ou o título exato divirjam)
    search_params = {'track_name': track_name, 'artist_name': artist_name}
    results = _request_json('https://lrclib.net/api/search?' + urllib.parse.urlencode(search_params))
    if results and isinstance(results, list):
        # Prioridade máxima para letras sincronizadas
        for item in results:
            if item.get('syncedLyrics'):
                return item['syncedLyrics'], 'sincronizada'
        if allow_plain:
            for item in results:
                if item.get('plainLyrics'):
                    return item['plainLyrics'], 'texto simples'

    return None, None

def sync_track_lyrics(item, original_file_path, target_file_path, artist):
    """
    Garante a presença do ficheiro .lrc para a faixa:
    1. Se já existir no destino com conteúdo, salta.
    2. Se existir junto ao ficheiro de origem no Plex, copia-o diretamente.
    3. Caso contrário, consulta a API LRCLIB (LRCGET) e cria o .lrc.
    """
    target_lrc = os.path.splitext(target_file_path)[0] + '.lrc'
    if os.path.exists(target_lrc) and os.path.getsize(target_lrc) > 0:
        return

    # 1. Verifica se já existe .lrc na pasta original da biblioteca do Plex
    original_lrc = os.path.splitext(original_file_path)[0] + '.lrc'
    if os.path.exists(original_lrc) and os.path.getsize(original_lrc) > 0:
        try:
            safe_copy_file(original_lrc, target_lrc)
            print(f"     [LRC] Copiado da biblioteca local: {os.path.basename(target_lrc)}")
            return
        except Exception as e:
            print(f"     [LRC] Erro ao copiar .lrc local: {e}")

    # 2. Descarrega via LRCLIB (mesma fonte do LRCGET)
    album = getattr(item, 'parentTitle', None)
    duration_sec = int((item.duration or 0) / 1000)

    try:
        lyrics_text, lyrics_type = fetch_lrclib_lyrics(
            track_name=item.title,
            artist_name=artist,
            album_name=album,
            duration_sec=duration_sec,
            allow_plain=FALLBACK_PLAIN_LYRICS
        )

        if lyrics_text:
            temp_lrc = target_lrc + '.part'
            with open(temp_lrc, 'w', encoding='utf-8') as f:
                f.write(lyrics_text.strip() + '\n')
            os.replace(temp_lrc, target_lrc)
            print(f"     [LRC] Letra ({lyrics_type}) transferida via LRCLIB: {os.path.basename(target_lrc)}")
        else:
            # Não polui a consola, mas regista que não encontrou
            pass
    except Exception as e:
        print(f"     [LRC] Erro ao obter letra para {item.title}: {e}")

def sync_plex_playlist():
    if not PLEX_TOKEN or PLEX_TOKEN == 'o_teu_token_do_plex':
        print("ERRO: Define o teu PLEX_TOKEN no ficheiro .env antes de executar.")
        return

    print(f"A ligar ao Plex em {PLEX_URL}...")
    try:
        plex = PlexServer(PLEX_URL, PLEX_TOKEN)
    except Exception as e:
        print(f"ERRO: Falha ao autenticar no servidor Plex: {e}")
        return
    
    media_dir = os.path.join(BASE_TARGET_DIR, MEDIA_SUBDIR)
    playlists_dir = os.path.join(BASE_TARGET_DIR, PLAYLISTS_SUBDIR)
    os.makedirs(media_dir, exist_ok=True)
    os.makedirs(playlists_dir, exist_ok=True)

    all_needed_files = set()

    for playlist_name in PLAYLISTS_TO_SYNC:
        print(f"\n--- A processar a playlist: {playlist_name} ---")

        try:
            playlist = plex.playlist(playlist_name)
        except Exception as e:
            print(f"Aviso: Playlist '{playlist_name}' não encontrada no Plex ({e}). A saltar...")
            continue

        m3u_path = os.path.join(playlists_dir, f"{playlist_name}.m3u")

        with open(m3u_path, 'w', encoding='utf-8') as m3u_file:
            m3u_file.write("#EXTM3U\n")

            for item in playlist.items():
                original_file_path = item.media[0].parts[0].file
                filename = os.path.basename(original_file_path)

                target_file_path = os.path.join(media_dir, filename)
                all_needed_files.add(filename)
                
                # Valida se o ficheiro de áudio já existe E se o tamanho é idêntico
                should_copy = True
                if os.path.exists(target_file_path):
                    try:
                        if os.path.getsize(target_file_path) == os.path.getsize(original_file_path):
                            should_copy = False
                    except OSError:
                        should_copy = True

                if should_copy:
                    print(f"  -> A copiar nova faixa: {filename}")
                    try:
                        safe_copy_file(original_file_path, target_file_path)
                    except Exception as e:
                        print(f"  -> Erro ao copiar {filename}: {e}")
                        continue

                duration_sec = int((item.duration or 0) / 1000)
                artist = (
                    getattr(item, 'originalTitle', None) 
                    or getattr(item, 'grandparentTitle', None) 
                    or "Unknown Artist"
                )

                # Obter / sincronizar letra sincronizada (.lrc)
                if SYNC_LYRICS:
                    sync_track_lyrics(item, original_file_path, target_file_path, artist)

                m3u_file.write(f"#EXTINF:{duration_sec},{artist} - {item.title}\n")

                # Usar barras normais '/' para máxima compatibilidade com leitores de automóveis
                relative_path = f"../{MEDIA_SUBDIR}/{filename}"
                m3u_file.write(f"{relative_path}\n")

    # --- LIMPEZA GERAL COM SUPORTE PARA .LRC ---
    print("\n--- A verificar remoções na pasta Media ---")
    
    # Extraímos apenas os nomes base (sem a extensão) de todas as músicas necessárias
    needed_base_names = {os.path.splitext(f)[0] for f in all_needed_files}

    for file in os.listdir(media_dir):
        # Ignora ficheiros temporários .part
        if file.endswith('.part'):
            continue

        base_name, ext = os.path.splitext(file)

        # Se o nome base não estiver na lista de músicas necessárias do Plex, apaga o ficheiro
        if base_name not in needed_base_names:
            file_to_remove = os.path.join(media_dir, file)
            print(f"  -> A remover ficheiro não necessário (ou órfão): {file}")
            try:
                os.remove(file_to_remove)
            except Exception as e:
                print(f"  -> Erro ao remover {file}: {e}")

    print("\nSincronização global concluída!")

if __name__ == '__main__':
    sync_plex_playlist()
