"""
VoxCPM2-palvelin (HTTP).

Lataa mallin kerran, kuuntelee 127.0.0.1:8179:ssä ja generoi+soittaa
wav-tiedostot saapuvien JSON-pyyntöjen mukaan.

Pyyntö: POST / sisällöllä
  {"text": "...", "ref": "anton.wav"|null, "voice": "..."|null,
   "play": true|false, "output": "polku"|null}

Vastaus:
  {"ok": true,  "outfile": "polku"}
  {"ok": false, "error": "viesti"}
"""

import json
import os
import platform
import subprocess
import sys
import threading
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ["TQDM_DISABLE"] = "1"

import soundfile as sf
from voxcpm import VoxCPM
from aanivalitsin import resolve_ref

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
HOSTI = "127.0.0.1"
PORTTI = 8179

_generate_lock = threading.Lock()


def soita(filepath):
    system = platform.system()
    if system == "Darwin":
        subprocess.run(["afplay", filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    elif system == "Linux":
        subprocess.run(["aplay", filepath], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def valitse_outfile(ref_path, output):
    if output:
        return output
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    voice_name = os.path.splitext(os.path.basename(ref_path))[0] if ref_path else "say"
    i = 1
    while True:
        outfile = os.path.join(OUTPUT_DIR, f"{voice_name}_{i:03d}.wav")
        if not os.path.exists(outfile):
            return outfile
        i += 1


def generoi(tts, req):
    text = req.get("text") or ""
    if not text.strip():
        raise ValueError("Tyhjä teksti")

    ref_arg = req.get("ref")
    voice = req.get("voice")
    output = req.get("output")
    play = req.get("play", True)

    ref_path = resolve_ref(ref_arg, pick=False) if ref_arg else None
    sample_rate = tts.tts_model.sample_rate

    kwargs = dict(text=text, cfg_value=2.0, inference_timesteps=10)
    if ref_path:
        kwargs["reference_wav_path"] = ref_path
    elif voice:
        kwargs["text"] = f"({voice}){text}"

    wav = tts.generate(**kwargs)
    outfile = valitse_outfile(ref_path, output)
    sf.write(outfile, wav, sample_rate)
    if play:
        soita(outfile)
    return outfile


class Kasittelija(BaseHTTPRequestHandler):
    tts = None

    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.address_string()}] {format % args}\n")

    def _vastaa(self, status, payload):
        body = (json.dumps(payload) + "\n").encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            data = self.rfile.read(length) if length else b""
            req = json.loads(data.decode("utf-8")) if data else {}
            with _generate_lock:
                outfile = generoi(self.tts, req)
            self._vastaa(200, {"ok": True, "outfile": outfile})
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            sys.stderr.flush()
            self._vastaa(500, {"ok": False, "error": f"{type(e).__name__}: {e}"})


def main():
    print("Ladataan VoxCPM2...", flush=True)
    Kasittelija.tts = VoxCPM.from_pretrained("openbmb/VoxCPM2", load_denoiser=False)
    print(f"Valmis. Kuunnellaan http://{HOSTI}:{PORTTI}", flush=True)

    palvelin = ThreadingHTTPServer((HOSTI, PORTTI), Kasittelija)

    try:
        palvelin.serve_forever()
    except KeyboardInterrupt:
        print("\nSammutetaan...", flush=True)
    finally:
        palvelin.server_close()


if __name__ == "__main__":
    main()
