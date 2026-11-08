"""Owner check so only you can command Jarvis. A convenience lock, not a security boundary: a photo or a
recording can fool it. Face: OpenCV YuNet + SFace (two small models download on first use).
Voice: Resemblyzer (optional, heavy: needs torch). Fails closed: if the check can't run, Jarvis refuses."""
import os
import time

from . import config

S = config.SETTINGS
DIR = config.DATA_DIR / "auth"
DIR.mkdir(exist_ok=True)
_BASE = "https://github.com/opencv/opencv_zoo/raw/main/models/"
MODELS = {
    "yunet": ("face_detection_yunet_2023mar.onnx", _BASE + "face_detection_yunet/face_detection_yunet_2023mar.onnx"),
    "sface": ("face_recognition_sface_2021dec.onnx", _BASE + "face_recognition_sface/face_recognition_sface_2021dec.onnx"),
}


def _model(key):
    name, url = MODELS[key]
    path = DIR / name
    if not path.exists():
        import requests
        print(f"Downloading {name} (one time)...")
        r = requests.get(url, timeout=180)
        r.raise_for_status()
        path.write_bytes(r.content)
    return str(path)


def _frame():
    import cv2
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW) if os.name == "nt" else cv2.VideoCapture(0)
    try:
        frame = None
        for _ in range(8):  # the first frames are dark while the camera warms up
            ok, f = cap.read()
            if ok:
                frame = f
            time.sleep(0.08)
        return frame
    finally:
        cap.release()


def _face_feature(frame):
    import cv2
    h, w = frame.shape[:2]
    det = cv2.FaceDetectorYN.create(_model("yunet"), "", (w, h), 0.8)
    _, faces = det.detect(frame)
    if faces is None or len(faces) == 0:
        return None
    face = max(faces, key=lambda f: f[2] * f[3])  # biggest face = the person at the keyboard
    rec = cv2.FaceRecognizerSF.create(_model("sface"), "")
    return rec.feature(rec.alignCrop(frame, face))


def enroll_face():
    import numpy as np
    feats = []
    print("Look at the camera. Capturing 5 shots, turn your head slightly between them...")
    for i in range(5):
        f = _face_feature(_frame())
        if f is None:
            print(f"  shot {i + 1}: no face found, try again with better light")
        else:
            feats.append(f)
            print(f"  shot {i + 1}: ok")
        time.sleep(0.8)
    if len(feats) < 3:
        return print("Not enough good shots. Face ID not saved.")
    np.save(DIR / "face.npy", np.array(feats))
    print("Face saved. Turn it on with JARVIS_AUTH=face in .env")


def enroll_voice(ears):
    import numpy as np
    from resemblyzer import VoiceEncoder, preprocess_wav
    enc, embs = VoiceEncoder(), []
    phrases = ["Jarvis, what is the weather like today?", "Open my project folder and show me the latest files.",
               "Remind me to call my mother this evening.", "Play some music and turn the volume down a little.",
               "Tell me the time and my first meeting tomorrow."]
    for p in phrases:
        print(f'Say: "{p}"')
        audio = ears.record_utterance(timeout=15)
        if audio is not None:
            embs.append(enc.embed_utterance(preprocess_wav(audio, source_sr=16000)))
    if len(embs) < 3:
        return print("Not enough clear samples. Voice ID not saved.")
    ref = np.mean(embs, axis=0)
    np.save(DIR / "voice.npy", ref / np.linalg.norm(ref))
    print("Voice saved. Turn it on with JARVIS_AUTH=voice in .env (use full sentences when it checks you).")


class Auth:
    def __init__(self):
        self._venc = None

    def face_ok(self):
        try:
            import cv2
            import numpy as np
            ref = DIR / "face.npy"
            if not ref.exists():
                return False, "Face ID isn't set up. Run: python main.py --enroll-face"
            feat = _face_feature(_frame())
            if feat is None:
                return False, "I can't see your face."
            rec = cv2.FaceRecognizerSF.create(_model("sface"), "")
            best = max(rec.match(f, feat, cv2.FaceRecognizerSF_FR_COSINE) for f in np.load(ref))
            return (best >= S.face_threshold), "I don't recognise you."
        except Exception as e:
            return False, f"Face check unavailable ({str(e)[:60]}). Install opencv-python."

    def voice_ok(self, audio):
        try:
            import numpy as np
            from resemblyzer import VoiceEncoder, preprocess_wav
            ref = DIR / "voice.npy"
            if not ref.exists():
                return False, "Voice ID isn't set up. Run: python main.py --enroll-voice"
            if audio is None:
                return False, "I didn't catch your voice."
            self._venc = self._venc or VoiceEncoder()
            emb = self._venc.embed_utterance(preprocess_wav(audio, source_sr=16000))
            sim = float(np.dot(emb, np.load(ref)) / np.linalg.norm(emb))
            return sim >= S.voice_threshold, "That doesn't sound like my owner."
        except Exception as e:
            return False, f"Voice check unavailable ({str(e)[:60]}). Install resemblyzer."

    def allow(self, audio):
        m = S.auth_mode
        if m == "voice":
            return self.voice_ok(audio)
        if m == "face":
            return self.face_ok()
        if m == "either":
            ok, why = self.voice_ok(audio)
            if ok:
                return True, ""
            ok2, why2 = self.face_ok()
            return (True, "") if ok2 else (False, why2 or why)
        if m == "both":
            ok, why = self.voice_ok(audio)
            return (False, why) if not ok else self.face_ok()
        return True, ""
