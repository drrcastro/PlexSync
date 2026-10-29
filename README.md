# 🎵 PlexSync — Car Music Exporter

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.9+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/Plex-Media%20Server-E5A00D?style=for-the-badge&logo=plex&logoColor=white" alt="Plex" />
  <img src="https://img.shields.io/badge/Storage-SMB%20%2F%20USB%20%2F%20exFAT-20B2AA?style=for-the-badge" alt="Storage" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=for-the-badge" alt="License" />
</p>

<p align="center">
  <strong>Sincronizador inteligente de playlists do Plex para pens USB e partilhas de rede (SMB), otimizado para sistemas de infoentretenimento de automóveis.</strong>
</p>

---

## 🚀 Sobre o Projeto

O **PlexSync** extrai faixas de música das tuas playlists favoritas do **Plex Media Server** e copia-as para uma pasta de destino (disco USB ou montagem SMB) de onde o sistema de som do carro lê diretamente.

Gera listas de reprodução em formato `.m3u` com caminhos relativos e faz a manutenção autónoma da biblioteca, eliminando faixas antigas ou órfãs.

### ✨ Funcionalidades Principais

- 🔄 **Sincronização Seletiva:** Exporta apenas as playlists configuradas (ex.: faixas favoritas `❤️ Tracks`, `Carro`, `Populares`).
- 🛡️ **Resiliente a FAT32 / exFAT / NTFS / SMB:** Cópia segura sem erros de permissão (`[Errno 1] Operation not permitted`), contornando limitações de atributos POSIX em discos externos e partilhas.
- ⚡ **Cópia Atómica e Verificação de Integridade:** As faixas são gravadas num ficheiro temporário (`.part`) e só assumidas quando completas. Se uma transferência for cancelada, na próxima execução o tamanho é comparado e a faixa recuperada.
- 📑 **Listas M3U Universais:** Cria ficheiros `.m3u` com caminhos relativos compatíveis com autorrádios e players de automóveis.
- 🧹 **Limpeza Automática:** Remove músicas da pasta que já não pertençam a nenhuma das playlists sincronizadas, preservando ficheiros de letras (`.lrc`).

---

## 📐 Arquitetura do Fluxo

```mermaid
flowchart LR
    Plex["🖥️ Plex Media Server<br/>(Playlists & Faixas)"] -->|plexapi| Script["⚙️ PlexSync Script"]
    Script -->|safe_copy_file| USB["📁 Destino SMB / USB<br/>/mnt/usb/musica_carro"]
    
    subgraph Destino
        USB --> Media["/Media/*.flac / *.mp3"]
        USB --> Playlists["/Playlists/*.m3u"]
    end
    
    Destino -->|Leitura SMB| Carro["🚗 Sistema de Som do Carro"]
```

---

## 📁 Estrutura de Diretórios Gerada

```text
/mnt/usb/musica_carro/
├── Media/
│   ├── 01 Song Name.flac
│   ├── 01 Song Name.lrc
│   └── 02 Another Song.mp3
└── Playlists/
    ├── ❤️ Tracks.m3u
    └── Carro.m3u
```

---

## 🛠️ Instalação e Preparação

### 1. Clonar o Repositório
```bash
git clone https://github.com/teu-utilizador/PlexSync.git
cd PlexSync
```

### 2. Criar e Ativar Ambiente Virtual
```bash
python3 -m venv venv_plex
source venv_plex/bin/activate
```

### 3. Instalar Dependências
```bash
pip install -r requirements.txt
```

---

## ⚙️ Configuração (.env)

Copia o ficheiro de exemplo para `.env`:
```bash
cp .env.example .env
```

Edita o `.env` com as tuas definições:
```env
# URL ou IP do teu servidor Plex
PLEX_URL=http://192.168.XXX.XXX:32400

# Token de autenticação do Plex
PLEX_TOKEN=o_teu_token_aqui

# Playlists a sincronizar (separadas por vírgula)
PLAYLISTS_TO_SYNC=Liked, Dance, Populares

# Pasta raiz de destino (disco USB montado ou partilha SMB)
BASE_TARGET_DIR=/mnt/usb/portable_player

# Sub-pastas (opcionais)
MEDIA_SUBDIR=Media
PLAYLISTS_SUBDIR=Playlists
```

### 🔍 Como obter o Plex Token?
1. Abre o Plex Web no browser e entra num álbum ou música.
2. Clica no menu dos três pontos (`...`) num item e seleciona **Get Info** (Obter informações).
3. Clica em **View XML** no canto inferior esquerdo.
4. Na barra de endereço do URL que abre, procura no final por `X-Plex-Token=...`. Esse valor é o teu token.

---

## ▶️ Execução

Para iniciar a sincronização manual:
```bash
python sync_playlist.py
```

### ⏰ Automatização (Cron Job)
Para manter as músicas do carro sempre atualizadas automaticamente todas as noites às 04:00:

```bash
crontab -e
```

Adiciona a linha:
```cron
0 4 * * * /root/PlexSync/venv_plex/bin/python /root/PlexSync/sync_playlist.py >> /var/log/plexsync.log 2>&1
```

---

## 🛡️ Licença

Distribuído sob a licença MIT. Consulta o ficheiro `LICENSE` para mais informações.

