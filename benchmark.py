import argparse
import os

from compress_nvenc_auto import RESOLUTIONS, run_ffmpeg


def benchmark_ffmpeg(input_file, encoder):
    import pandas as pd
    import matplotlib.pyplot as plt

    output_dir = "results"
    # qp_range = range(QP_MIN, QP_MAX + 1, 5)
    qp_range = [40]

    os.makedirs(output_dir, exist_ok=True)
    data = []

    try:
        # === BOUCLE DE TEST ===
        for label, value in RESOLUTIONS.items():
            scale, fps, ab = value
            print(f"\n===> Résolution {label} ({scale}@{fps}) <===")
            for qp in qp_range:
                out = os.path.join(output_dir, f"{label}_qp{qp}.mp4")
                size = run_ffmpeg(input_file, out, qp=qp, scale=scale, fps=fps, audio_bitrate=ab, encoder=encoder)
                os.remove(out)
                print(f"QP={qp} → {size / 1024 / 1024:.2f} Mo")
                data.append({
                    "resolution": label,
                    "qp": qp,
                    "size_mb": size
                })
    except KeyboardInterrupt:
        print("\n⏹️ Interruption manuelle détectée, on termine proprement...")

    finally:
        if not data:
            print("⚠️ Aucun résultat à enregistrer.")
            return

        # === SAUVEGARDE ===
        df = pd.DataFrame(data)
        csv_path = os.path.join(output_dir, "results.csv")
        df.to_csv(csv_path, index=False)
        print(f"\nRésultats enregistrés dans : {csv_path}")

        # === PLOT ===
        plt.figure(figsize=(10, 6))
        for label, group in df.groupby("resolution"):
            plt.plot(group["qp"], group["size_mb"], marker="o", label=label)

        plt.gca().invert_xaxis()  # QP ↑ → taille ↓
        plt.xlabel("QP (Quantizer Parameter)")
        plt.ylabel("Taille du fichier (Mo)")
        plt.title("Relation entre QP et taille de la vidéo")
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(os.path.join(output_dir, "qp_curve.png"))
        plt.show()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compression automatique GPU NVENC vers une taille cible")
    parser.add_argument("input", help="Fichier vidéo source")
    parser.add_argument("target", help="Taille cible (ex: 10M, 500K, 1G)")
    parser.add_argument("--encoder", choices=["h264", "hevc"], default="h264",
                        help="Encodeur NVENC à utiliser (défaut: h264)")

    args = parser.parse_args()
    benchmark_ffmpeg(args.input, args.encoder)