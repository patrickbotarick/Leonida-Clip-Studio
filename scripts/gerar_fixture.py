"""Cria apenas mídia sintética identificada para validação; não cria projetos."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.media import binary, NO_WINDOW

folder = ROOT / '.local/fixtures'
folder.mkdir(parents=True, exist_ok=True)
video = folder / 'Validacao sintetica - duas faixas.mp4'
if not video.exists():
    subprocess.run([binary('ffmpeg'), '-v', 'error', '-n', '-f', 'lavfi', '-i', 'testsrc2=size=640x360:rate=30000/1001',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:sample_rate=48000',
                    '-f', 'lavfi', '-i', 'sine=frequency=880:sample_rate=48000', '-t', '12',
                    '-map', '0:v', '-map', '1:a', '-map', '2:a', '-c:v', 'libx264', '-preset', 'ultrafast',
                    '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-metadata:s:a:0', 'handler_name=Microfone sintetico (440 Hz)',
                    '-metadata:s:a:1', 'handler_name=Jogo sintetico (880 Hz)', '-movflags', '+faststart', str(video)], check=True, timeout=30, creationflags=NO_WINDOW)
subtitle = folder / 'Validacao sintetica.srt'
if not subtitle.exists():
    subtitle.write_text('1\n00:00:00,500 --> 00:00:03,000\nMídia sintética de validação. Não é uma transcrição real.\n\n2\n00:00:03,500 --> 00:00:06,000\nFaixa 1: tom de 440 Hz. Faixa 2: tom de 880 Hz.\n\n3\n00:00:07,000 --> 00:00:10,500\nClique neste trecho para testar a navegação sincronizada.\n', encoding='utf-8')
print(video)
print(subtitle)
