import json
import sys
from pathlib import Path

from .transcription_worker import emit
from .waveform import generate

if __name__ == '__main__':
    request = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    generate(request, emit)
    emit(stage='completed', progress=100)
