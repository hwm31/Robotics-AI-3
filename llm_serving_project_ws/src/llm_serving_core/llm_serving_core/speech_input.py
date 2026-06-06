"""Google STT 기반 푸시투토크 음성 입력."""

from __future__ import annotations


class SpeechInputError(Exception):
    """음성 입력 초기화 또는 인식 실패."""


class SpeechInputHandler:
    def __init__(
        self,
        language: str = 'ko-KR',
        ambient_noise_duration: float = 0.5,
    ):
        try:
            import speech_recognition as sr
        except ImportError as exc:
            raise SpeechInputError(
                'SpeechRecognition 패키지가 필요합니다: pip install SpeechRecognition PyAudio'
            ) from exc

        self._sr = sr
        self.language = language
        self.ambient_noise_duration = ambient_noise_duration
        self.recognizer = sr.Recognizer()
        try:
            self.microphone = sr.Microphone()
        except Exception as exc:
            raise SpeechInputError(
                '마이크를 열 수 없습니다. PyAudio와 portaudio가 설치되어 있는지 확인하세요.'
            ) from exc
        self._ambient_adjusted = False

    def listen_once(self) -> str | None:
        """한 번 녹음 후 텍스트를 반환합니다. 인식 실패 시 None."""
        with self.microphone as source:
            if not self._ambient_adjusted:
                self.recognizer.adjust_for_ambient_noise(
                    source, duration=self.ambient_noise_duration)
                self._ambient_adjusted = True

            audio = self.recognizer.listen(source)

        try:
            return self.recognizer.recognize_google(audio, language=self.language)
        except self._sr.UnknownValueError:
            return None
        except self._sr.RequestError as exc:
            raise SpeechInputError(f'Google STT 요청 실패: {exc}') from exc
