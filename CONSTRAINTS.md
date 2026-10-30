# CONSTRAINTS

Catchtype Windows판의 단어 목록을 터미널 명령으로 고치는 개인용 도구.

## 대상과 위치
- Catchtype Windows판(이 PC)과 Mac판을 다룬다. Mac판은 다른 사람이 시험해 준다.
- 코드는 `C:\Users\user\catchtype-words`에 두고, 같은 이름의 GitHub 공개 저장소에 올린다.
- 공개 저장소에는 개인 단어 목록(`my-words.json`), Catchtype 내장 사전(`.cache/`), 개인 경로나 계정 정보를 올리지 않는다.

## 기능
- 네 가지만 한다: 늘 바꿀 말 추가, 그대로 둘 말 추가, 배운 말 지우기, 목록 보기.
- 단어는 화면에 나온 한글 모양(예: `채며쇅`)으로도, 원래 치려던 영문 키(예: `coauthor`)로도 받는다.
- Catchtype 종료와 재시작은 도구가 처리한다.

## 설정 파일 다루기
- Catchtype이 실제로 읽는 설정은 `%APPDATA%\Catchtype\settings.json`이다.
- 바꾸기 전에는 늘 백업하고, 바꾼 뒤에는 단어 목록 사본을 `my-words.json`에 남긴다. 이 파일은 git에 올리지 않는다.
- Mac판은 `com.hebbianai.catchtype` 환경설정에 같은 세 목록을 같은 형식으로 둔다. plist 파일을 직접 고치지 않고 `defaults export`/`import`로만 읽고 쓴다.
- 설정 형식은 공식 문서가 없으므로, 예상과 다르면 아무것도 쓰지 않고 멈춘다.

## 실행 환경
- 이미 설치된 Python만 쓰고, 외부 패키지는 설치하지 않는다.
- Mac에서는 시스템 `python3`(3.9)에서도 돌아가야 한다.

## 범위 밖
- 앱마다 다른 규칙, 내장 사전 수정, 다른 사람을 위한 설치 지원이나 배포 패키지, Linux 지원, 논문 파일에서 걸릴 단어 미리 찾기.
