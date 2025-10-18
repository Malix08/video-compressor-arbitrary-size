import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

# === CONFIGURATION ===
csv_path = "results/results.csv"
target_size_mb = 10 * 1024**2  # taille cible à prédire

# === Fonction exponentielle ===
def exp_func(qp, a, b):
    return a * np.exp(-b * qp)

# === Lecture du CSV ===
df = pd.read_csv(csv_path)

predictions = []

plt.figure(figsize=(10, 6))

for label, group in df.groupby("resolution"):
    qp = group["qp"].values
    size = group["size_mb"].values

    # Régression exponentielle
    popt, _ = curve_fit(exp_func, qp, size, p0=(max(size), 0.1))
    a, b = popt
    print(a, b)

    # Prédiction du QP pour une taille cible
    qp_pred = -np.log(target_size_mb / a) / b
    predictions.append((label, qp_pred))

    # Affichage de la courbe
    qp_fit = np.linspace(min(qp), max(qp), 100)
    size_fit = exp_func(qp_fit, *popt)
    plt.plot(qp, size, "o", label=f"{label} data")
    plt.plot(qp_fit, size_fit, "-", label=f"{label} fit")

plt.gca().invert_xaxis()
plt.xlabel("QP (Quantizer Parameter)")
plt.ylabel("Taille du fichier (Mo)")
plt.title("Régression exponentielle QP → taille")
plt.legend()
plt.grid(True)
plt.tight_layout()

# === Affichage des prédictions ===
print("\n📈 Estimation du QP pour atteindre ~10 Mo :")
for label, qp_pred in predictions:
    print(f"  {label:<8}  →  QP ≈ {qp_pred:.2f}")

plt.show()