# catchtype-words

Catchtype의 단어 목록을 터미널에서 고치는 개인용 도구예요.
Windows판에는 Mac판의 "무조건 바꿀 말" 같은 목록 화면이 없어서 만들었어요.
Catchtype Windows판(0.3.0-beta.9.1)과 Mac판(0.3.0)에서 확인했어요.
Mac판은 설정 화면에서 같은 목록을 고칠 수 있어요. 그걸로 충분하면 이 도구는 필요 없어요.

## 준비

- 이미 설치된 Python만 쓰고, 따로 설치할 패키지는 없어요. Mac에서는 시스템 `python3`(3.9 이상)로 돌아요.
- Windows: 이 폴더가 사용자 PATH에 들어 있어서 어느 터미널에서든 `ct`로 실행해요.
- Mac: 받은 뒤 `ct` 별칭을 만들어요. 계속 쓰려면 별칭 줄을 `~/.zshrc`에도 넣어요.

```
git clone https://github.com/hyukjunlim/catchtype-words.git ~/catchtype-words
alias ct='python3 -I ~/catchtype-words/ct.py'
```

## 낱말마다 정하는 것

키 순서 하나마다 아래 넷 중 하나를 정해요.

| 정하는 것 | 영어 상태로 칠 때 | 한글 상태로 칠 때 | 명령 |
|---|---|---|---|
| Catchtype이 판단 (기본) | Catchtype이 정함 | Catchtype이 정함 | `ct forget` |
| 늘 영어 말로 (예: wsl) | wsl | ㅈ니 → wsl | `ct add` |
| 늘 한글 말로 (예: 안녕) | dkssud → 안녕 | 안녕 | `ct add` |
| 친 그대로 (예: wls / 진) | wls | 진 | `ct keep` |

반대쪽 모양도 내가 쓰는 말이면 `ct keep`, 아니면 `ct add`를 써요.

## 명령

```
ct add 채며쇅     한글 상태에서 친 채며쇅을 늘 coauthor로 (ct add coauthor 도 같아요)
ct keep wls       영어 상태에선 wls, 한글 상태에선 진, 친 그대로
ct forget absy    어느 목록에서든 지우기
ct list           지금 목록 보기
```

- 낱말은 화면에 나온 한글 모양으로도, 원래 치려던 영문 키로도 넣을 수 있어요.
- `ct add`는 두 해석을 보여 주고, 추측한 쪽을 Enter로 확인받아요.
  `--en`(영어가 남게)이나 `--ko`(한글이 남게)를 붙이면 묻지 않아요.

## 목록 읽기

- **늘 바꿀 말**: `ct add`로 넣은 말이에요. 반대 상태에서 친 같은 키는 그대로 둬요.
- **그대로 둘 말**: "어느 상태든 친 그대로"는 `ct keep`으로 넣은 말이에요.
  "○○ 상태에서 칠 때만"은 같은 바꿈을 세 번 되돌린 걸 보고 Catchtype이 스스로 배운 말이에요.
- **배우는 중**: 한두 번 되돌린 말이에요. 세 번이 되면 그대로 둘 말로 옮겨 가요.

## 동작 방식

Catchtype은 Windows와 Mac에서 같은 세 목록을 같은 형식으로 저장해요.
공식 문서가 없어서, 아래 내용은 직접 확인한 거예요.

| | Windows | Mac |
|---|---|---|
| 설정 | `%APPDATA%\Catchtype\settings.json` | 환경설정 `com.hebbianai.catchtype` (`defaults`로 읽고 써요) |
| 고치기 전 백업 (최근 30개) | `%APPDATA%\Catchtype\ct-backups` | `~/Library/Application Support/Catchtype/ct-backups` |

| 항목 | 형식 | 뜻 |
|---|---|---|
| `alwaysConvertedWords` | `상태\t키\t시각` | 그 상태에서 친 키를 늘 다른 언어로 바꿈 |
| `undoneWords` | `횟수\t상태\t키` | 그 바꿈을 되돌린 횟수 (3번이면 친 그대로 둠) |
| `learnedWordDates` | `상태\t키\t시각` | 친 그대로 두게 된 시각 |

상태는 키를 칠 때의 입력 상태(`korean`/`english`)이고, 키는 실제로 누른 영문 키예요.

- Catchtype이 켜져 있으면 설정을 다시 덮어써요. 그래서 바꿀 때마다 잠깐 끄고, 고친 뒤 다시 켜요.
  Windows판은 보통 종료 요청을 무시해서 강제로 끄고, Mac판은 보통대로 종료해요.
- 설정 형식이 예상과 다르면(예: Catchtype 업데이트) 아무것도 쓰지 않고 멈춰요.
- 실제 설정을 바꾸거나 `ct list`를 할 때마다 세 목록 사본을 `my-words.json`에 남겨요. 개인 단어가 담기므로 git에는 올리지 않아요.

## 되돌리기

- Windows: Catchtype을 끄고, `ct-backups`에서 원하는 파일을 `settings.json` 자리에 복사한 뒤 다시 켜요.
- Mac: Catchtype을 끄고, 아래 명령을 친 뒤 다시 켜요.

```
defaults import com.hebbianai.catchtype <백업 파일>
```

## 파일

- `ct.py`: 도구 본체
- `ct.cmd`: Windows에서 `ct` 명령으로 실행하게 해 주는 파일
- `my-words.json`: 지금 목록의 사본 (git에 올리지 않음)
- `CONSTRAINTS.md`: 이 도구가 지키는 범위와 규칙
