import whisper
model = whisper.load_model("tiny", device="cuda")  # ou device="cuda:0"
print(model.device)