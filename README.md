# 🎬 숏폼 마케팅 도우미

마케팅 담당자가 없는 소상공인·작은 브랜드를 위한 AI 웹서비스입니다.
제품 정보를 입력하면 생성형 AI(Google Gemini)가 **쇼츠 대본, 제목 후보, 설명란, 해시태그, 인스타그램 글**을 만들고,
댓글을 붙여 넣으면 **분류(문의·칭찬·불만·민감·스팸)와 답글 초안**을 만듭니다.

## 핵심 기능
| 기능 | 입력 | AI 처리 | 결과 |
|---|---|---|---|
| 쇼츠 대본 | 제품명·특징·가격·대상·이벤트, 말투, 구성 방식, 길이 | Gemini가 JSON으로 대본 생성 | 장면별 화면 문구·나레이션, 제목 3개, 설명란, 해시태그, 인스타 글 |
| 자동 검사 | AI 결과 | 규칙 검사 (AI 아님) | 금지·과장·효능 표현, 지시문, 입력에 없는 숫자, 길이 경고 |
| 댓글 응대 | 댓글 여러 개 | Gemini가 분류·답글 작성 | 분류 통계, 답글 초안 (불만·민감은 답글 없이 담당자에게) |

## 안전장치
- API 키는 서버 측(Streamlit Secrets)에만 보관. 코드·화면에 없음
- 입력에 전화번호·이메일 등이 있으면 대본 생성을 막고, 댓글은 가린 뒤 AI에 전송
- AI가 불만·민감 댓글에 답글을 써도 화면에서 숨김 (AI 규칙 위반 대비 이중 장치)
- AI 호출 실패(키 오류, 한도 초과, 형식 오류, 네트워크) 시 한국어 안내 메시지
- 한 사용자가 10분에 15번 넘게 요청하면 잠시 제한 (무료 한도 보호)

## 파일 구성
```
app.py                 화면 (Streamlit)
ai.py                  Gemini 호출, 오류 처리, 대체 모델
prompts.py             AI 지시문
checks.py              결과 검사기, 개인정보 감지, 댓글 규칙 강제
tests/test_app.py      가짜 AI 응답으로 화면·예외 시험 (실제 API 호출 없음)
requirements.txt       필요한 패키지
.streamlit/secrets.toml.example   키 설정 예시
```

---

## 배포 방법 (Streamlit Community Cloud, 무료)

### 1. Gemini API 키 받기
1. https://aistudio.google.com 에 구글 계정으로 로그인
2. **Get API key → Create API key**
3. 키를 복사해 둡니다. **이 키는 비밀번호와 같아서 코드나 채팅방에 올리면 안 됩니다.**

### 2. GitHub에 코드 올리기
1. https://github.com 가입 → 오른쪽 위 **+ → New repository**
2. 이름 예: `shortform-helper`, **Public**, **Create repository**
3. **uploading an existing file** 링크를 눌러 이 폴더의 파일을 끌어다 놓기
   - `.streamlit` 폴더도 함께 올립니다 (`config.toml`, `secrets.toml.example`)
   - **`secrets.toml`(진짜 키가 든 파일)은 절대 올리지 않습니다**
4. **Commit changes**

### 3. Streamlit Cloud에 배포
1. https://share.streamlit.io 에 GitHub 계정으로 로그인
2. **Create app → Deploy a public app from GitHub**
3. Repository: 방금 만든 저장소, Branch: `main`, Main file path: `app.py`
4. **Advanced settings → Secrets**에 아래를 붙여 넣기
   ```
   GEMINI_API_KEY = "복사한_키"
   ```
5. **Deploy** → 1~3분 뒤 `https://○○○.streamlit.app` 주소가 생깁니다

### 4. 확인 (과제 필수 항목)
- 휴대폰이나 **시크릿 창**에서 주소를 열어 봅니다
- 예시 제품으로 대본 생성 → 입력을 바꿔 다시 생성 → 결과가 달라지는지 확인
- 예시 댓글로 분류 → 불만 댓글에 답글이 없는지 확인

### 키를 바꾸거나 모델을 바꾸려면
Streamlit Cloud 앱 화면 오른쪽 아래 **Manage app → ⋮ → Settings → Secrets**에서 수정합니다.
`GEMINI_MODEL = "모델 이름"`을 추가하면 다른 Gemini 모델을 쓸 수 있습니다.

---

## 내 PC에서 실행해 보기
```bash
pip install -r requirements.txt
# .streamlit/secrets.toml.example을 복사해 secrets.toml로 만들고 키 입력
streamlit run app.py
```
테스트(실제 AI 호출 없음): `python tests/test_app.py`

## 한계
- AI는 사실과 다른 내용을 만들 수 있으며, 검사기는 형식·표현만 확인합니다. 게시 전 사람의 확인이 필요합니다.
- 무료 API는 사용량 한도가 있어 요청이 몰리면 잠시 실패할 수 있습니다.
- 광고 규정은 업종·시기에 따라 다르므로 실제 게시 전 확인이 필요합니다.
