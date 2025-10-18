import argparse
import json
import math
import os
import subprocess
from functools import reduce
from pathlib import Path

# ==========================
# 🔧 CONFIGURATION GLOBALE
# ==========================

# Format : [("nom", "largeur:hauteur" ou None, fps ou None)]
# fps=None → garde la fréquence d'image originale
RESOLUTIONS = {
    # "original": (None, None, None),
    "1080p60-128k": ("1920:1080", 60, "194k"),
    "720p60-128k": ("1280:720", 60, "128k"),
    "480p30-64k": ("854:480", 30, "64k"),
    "360p30-64k": ("640:360", 30, "64k"),
    "240p30-32k": ("426:240", 30, "32k"),
    "144p30-16k": ("256:144", 30, "16k"),
}

QP_MIN = 20
QP_MAX = 40
FFMPEG_PATH = "C:\\Program Files\\Shotcut\\ffmpeg.exe"
FFPROBE_PATH = "C:\\Program Files\\Shotcut\\ffprobe.exe"


# ==========================
# 🧰 OUTILS
# ==========================

def human_to_bytes(size_str: str)-> int:
    """Convertit 10M / 500K / 1G en octets"""
    size_str = size_str.strip().upper()
    if size_str.endswith("O"):
        size_str = size_str[:-1]
    if size_str.endswith('G'):
        return int(float(size_str[:-1]) * 1024 ** 3)
    if size_str.endswith('M'):
        return int(float(size_str[:-1]) * 1024 ** 2)
    if size_str.endswith('K'):
        return int(float(size_str[:-1]) * 1024)
    return int(size_str)

def get_size(path: Path)-> int:
    """Retourne la taille du fichier en octets"""
    return os.path.getsize(path)

def get_video_info(path: Path) -> dict[str, None]:
    cmd = [
        FFPROBE_PATH, "-v", "error",
        "-show_entries", "stream",
        "-of", "json",
        path
    ]
    out = subprocess.check_output(cmd, text=True)
    data = json.loads(out)

    info = {}
    streams = data.get("streams", [])

    # Cherche le premier stream vidéo et audio
    v = next((s for s in streams if s.get("codec_type") == "video"), None)
    if v:
        info["width"] = int(v.get("width")) if v.get("width") else None
        info["height"] = int(v.get("height")) if v.get("height") else None
    return info

def run_ffmpeg(input_file, output_file, qp, scale, fps, audio_bitrate, encoder="h264"):
    """Encode une vidéo temporaire avec FFmpeg + NVENC"""
    filters = []

    if scale:
        filters.append(f"scale={scale}")
    if fps:
        filters.append(f"fps={fps}")
    vf = ",".join(filters)

    codec = "h264_nvenc" if encoder == "h264" else "hevc_nvenc"

    cmd = [
        FFMPEG_PATH,
        "-loglevel", "error", "-stats", "-hide_banner",
        "-y", "-i", input_file,
        "-c:v", codec,
        "-rc", "constqp",
        "-qp", str(qp),
        "-preset", "p5",
    ]

    # Ajoute le filtre uniquement si nécessaire
    if vf:
        cmd += ["-vf", vf]

    if audio_bitrate is not None:
        cmd += ["-c:a", "aac", "-b:a", audio_bitrate]

    cmd += [
        "-movflags", "+faststart",
        output_file
    ]

    subprocess.run(cmd)
    return get_size(output_file)


# ==========================
# ⚙️ LOGIQUE PRINCIPALE
# ==========================

def compress_auto(input_file, target_str, encoder):
    tmp_dir = "_predict_tmp"
    os.makedirs(tmp_dir, exist_ok=True)

    target_size = human_to_bytes(target_str)
    print(f"🎯 Objectif : {target_size / 1024 ** 2:.2f} Mo")

    qp0 = 40
    chosen_name, chosen_size0 = "", 0
    tmp0 = os.path.join(tmp_dir, f"p0_q{qp0}.mp4")

    video_infos = get_video_info(args.input)
    original_res = f"{video_infos['width']}:{video_infos['height']}"
    try:
        idx = list(map(lambda a: a[0], RESOLUTIONS.values())).index(original_res)
    except ValueError:
        idx = 0

    # trouver la plus haute résolution qui rentre
    items = list(RESOLUTIONS.items())
    nb_pixel_list = list(map(lambda res: reduce(lambda x, y: x*y, map(int, res[1][0].split(":")), 1), items))
    name, (res, fps, ab) = items[idx]
    print(f"🧪 Test {name} ({res or 'original'}) @ {fps or 'source'}fps - {ab or 'source'} audio, QP={qp0}")
    size0 = run_ffmpeg(input_file, tmp0, qp=qp0, scale=res, fps=fps, audio_bitrate=ab, encoder=encoder)
    print(f"   → Taille = {size0 / 1024 ** 2:.2f} Mo")

    if size0 <= target_size:
        chosen_name, chosen_size0 = name, size0
        print(f"✅ OK : résolution/fps choisis = {name} @ {fps or 'source'}fps - {ab or 'source'} audio\n")
    else:
        coef = size0 / nb_pixel_list[idx]
        i = None
        for i in range(idx + 1, len(items)):
            pred_size = coef * nb_pixel_list[i]
            if pred_size <= target_size:
                name, (res, fps, ab) = items[i]
                print(f"🧪 Prédiction de la taille avec coef:{coef:.2f} => {name} ({res or 'original'}) @ {fps or 'source'}fps - {ab or 'source'} audio, QP={qp0}")
                print(f"   → Taille = {pred_size / 1024 ** 2:.2f} Mo")
                break
        if i == len(items):
            print("❌ Même en 144p/30fps, la vidéo dépasse la taille cible (essaie un QP > 40 ou une taille plus grande)")
            return

        for i in range(i, len(items)):
            name, (res, fps, ab) = items[i]
            print(f"🧪 Test {name} ({res or 'original'}) @ {fps or 'source'}fps - {ab or 'source'} audio, QP={qp0}")
            size0 = run_ffmpeg(input_file, tmp0, qp=qp0, scale=res, fps=fps, audio_bitrate=ab, encoder=encoder)
            print(f"   → Taille = {size0 / 1024 ** 2:.2f} Mo")
            if size0 <= target_size:
                chosen_name, chosen_size0 = name, size0
                print(f"✅ OK : résolution/fps choisis = {name} @ {fps or 'source'}fps - {ab or 'source'} audio\n")
                break

    if chosen_name == "" or chosen_size0 == 0:
        print("❌ Même en 144p/30fps, la vidéo dépasse la taille cible (essaie un QP > 40 ou une taille plus grande)")
        return

    predict_qp_workflow(
        input_file=input_file,
        target_size=target_size,
        encoder=encoder,
        profile_name=chosen_name,
        tmp_dir=tmp_dir,
        tmp0=tmp0,
        size0=chosen_size0,
        qp0=qp0
    )

    for f in os.listdir(tmp_dir):
        try:
            os.remove(os.path.join(tmp_dir, f))
        except:
            pass
    try:
        os.rmdir(tmp_dir)
    except:
        pass


def predict_qp_workflow(input_file, target_size, encoder, profile_name, tmp_dir, tmp0, size0, qp0=40, qp1=30):
    scale, fps, ab = RESOLUTIONS[profile_name]
    # estimate b from second probe
    tmp1 = os.path.join(tmp_dir, f"p1_q{qp1}.mp4")
    print(f"\nRunning second probe QP={qp1} ... (temp: {tmp1})")
    size1 = run_ffmpeg(input_file, tmp1, qp=qp1, scale=scale, fps=fps, audio_bitrate=ab, encoder=encoder)
    print(f" -> size at QP={qp1}: {size1 / 1024 ** 2:.2f} Mo")
    # b = - ln(p1/p0) / (q1 - q0)
    b = -math.log(size1 / size0) / (qp1 - qp0)
    print(f"Estimated b from probes: {b:.5f}")

    # predict QP
    S_t = target_size
    p0 = size0
    if S_t <= 0:
        raise Exception("Target must be > 0")

    ratio = S_t / p0
    # safeguard ratio > 0
    if ratio <= 0:
        raise Exception("Erreur: ratio target/p0 invalid.")

    qp_pred = qp0 - math.log(ratio) / b  # derived formula
    qp_ciel = math.ceil(qp_pred)
    qp_ciel = max(QP_MIN, min(QP_MAX, qp_ciel))
    print(f"Clamped/ceil predicted QP = {qp_ciel} (was {qp_pred:.2f})")

    final_tmp = None
    final_size = None
    cur_qp = qp_ciel
    if qp_ciel == qp0:
        final_tmp = tmp0
        final_size = size0
    if qp_ciel == qp1:
        final_tmp = tmp1
        final_size = size1

    if final_tmp is None:
        # run final encode at predicted QP to verify
        final_tmp = os.path.join(tmp_dir, f"final_q{qp_ciel}.mp4")
        print(f"\nEncoding final candidate at QP={cur_qp} ...")
        final_size = run_ffmpeg(input_file, final_tmp, qp=cur_qp, scale=scale, fps=fps, audio_bitrate=ab,
                                encoder=encoder)
        print(f" -> size = {final_size / 1024 ** 2:.2f} Mo  (target {target_size / 1024 ** 2:.2f} Mo)")

        # if result > target, increase QP stepwise until <= target or reach QP_MAX
        while final_size > target_size and cur_qp < QP_MAX:
            cur_qp += 1
            print(f"Candidate too large, trying QP={cur_qp} ...")
            if os.path.exists(final_tmp):
                try:
                    os.remove(final_tmp)
                except:
                    pass
            cand_tmp = os.path.join(tmp_dir, f"final_q{cur_qp}.mp4")
            final_size = run_ffmpeg(input_file, cand_tmp, qp=cur_qp, scale=scale, fps=fps, audio_bitrate=ab,
                                    encoder=encoder)
            print(f" -> size = {final_size / 1024 ** 2:.2f} Mo")
            # replace final_tmp with new best
            final_tmp = cand_tmp

    # done
    if final_size <= target_size:
        # get input filename without extension to create output filename
        out_name = f"{Path(input_file).name}_{profile_name}_q{cur_qp}.mp4"
        os.replace(final_tmp, out_name)
        print(f"\nSuccess! final file saved as: {out_name} (QP={cur_qp}, size={final_size / 1024 ** 2:.2f} Mo)")
    else:
        print("\nPrediction failed to reach target even at max QP.")
        print(f"Best result: QP={cur_qp}, size={final_size / 1024 ** 2:.2f} Mo")
        # keep the file for inspection
        out_name = f"best_q{cur_qp}_{encoder}.mp4"
        os.replace(final_tmp, out_name)
        print(f"Saved best candidate as {out_name}")


# ==========================
# 🚀 EXÉCUTION
# ==========================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compression automatique GPU NVENC vers une taille cible")
    parser.add_argument("input", help="Fichier vidéo source")
    parser.add_argument("target", help="Taille cible (ex: 10M, 500K, 1G)")
    parser.add_argument("--encoder", choices=["h264", "hevc"], default="h264",
                        help="Encodeur NVENC à utiliser (défaut: h264)")

    args = parser.parse_args()
    compress_auto(args.input, args.target, args.encoder)


