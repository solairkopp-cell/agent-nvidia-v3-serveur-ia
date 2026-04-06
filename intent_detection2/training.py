import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report
import pickle

# Load
df = pd.read_csv("intentions.csv")
df.columns = ["intent", "text"]

# Encode
print("Encoding...")
model = SentenceTransformer("paraphrase-MiniLM-L6-v2")
X = model.encode(df["text"].tolist(), show_progress_bar=True)
y = df["intent"].tolist()

# Train
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
clf = LogisticRegression(max_iter=1000)
clf.fit(X_train, y_train)

# Eval
print(classification_report(y_test, clf.predict(X_test)))

# Save
pickle.dump(clf, open("intent_clf.pkl", "wb"))
model.save("intent_embedder")
print("Done.")