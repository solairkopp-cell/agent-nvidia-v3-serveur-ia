import pickle
from sentence_transformers import SentenceTransformer


class IntentService:
    def __init__(self, model_path="intent_embedder", clf_path="intent_clf.pkl"):
        self.embedder = SentenceTransformer(model_path)
        self.clf = pickle.load(open(clf_path, "rb"))

    def predict(self, text: str) -> str:
        vec = self.embedder.encode([text])
        return self.clf.predict(vec)[0]

    def predict_proba(self, text: str) -> dict:
        vec = self.embedder.encode([text])
        probs = self.clf.predict_proba(vec)[0]
        return dict(zip(self.clf.classes_, probs))