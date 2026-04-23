import onnxruntime as ort

try:
    # On tente d'instancier un moteur vide sur CUDA
    sess = ort.InferenceSession(None, providers=['CUDAExecutionProvider'])
    print("Succès : CUDA est disponible !")
except Exception as e:
    print(f"Erreur détaillée : {e}")

print("Providers disponibles :", ort.get_available_providers())