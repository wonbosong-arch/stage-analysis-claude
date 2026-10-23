[설치 순서 - 한 번만]
1. github.com 가입 -> New repository -> 이름 stage-analysis, Public 선택 -> 생성
2. 이 폴더의 파일 전체(.github 폴더 포함)를 저장소에 업로드 (Add file > Upload files, 폴더째 드래그)
   * .github 폴더가 숨김 처리돼 안 보이면 압축을 푼 뒤 폴더째 끌어다 놓으세요
3. 저장소 Settings > Secrets and variables > Actions > New repository secret
   KIS_APP_KEY = 한투 앱키 / KIS_APP_SECRET = 한투 시크릿 (코드나 채팅에는 절대 쓰지 마세요)
4. Settings > Pages > Source 를 "GitHub Actions" 로 변경
5. Actions 탭 > daily-stage-analysis > Run workflow (첫 실행, 이후 평일 오전 8시 자동)
6. 완료 후 Settings > Pages 에 표시되는 주소가 대시보드 링크입니다
