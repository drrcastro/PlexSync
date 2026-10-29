import os
import shutil
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
                
                # Valida se o ficheiro já existe E se o tamanho é idêntico
                # (evita ignorar ficheiros corrompidos ou cópias canceladas a meio)
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
