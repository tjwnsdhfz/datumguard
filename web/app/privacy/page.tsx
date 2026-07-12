import Link from "next/link";

import "./privacy.css";
import LocalDataControls from "./local-data-controls";

export default function PrivacyPage() {
  return (
    <main className="privacy-shell">
      <header>
        <Link href="/" className="privacy-brand">DG / DATUMGUARD</Link>
        <Link href="/intake">Artifact Lab로 돌아가기</Link>
      </header>
      <section className="privacy-hero">
        <span>PRIVACY / LOCAL DATA / 2026-07</span>
        <h1>비기밀 CAD만<br />처리하세요.</h1>
        <p>DatumGuard 공개 데모는 계정이나 장기 프로젝트 저장소가 아닙니다. 고객 기밀, 개인정보, 수출통제, 의료·방산·규제 대상 파일은 업로드하지 마세요.</p>
      </section>
      <section className="privacy-grid">
        <article>
          <span>01 / SERVER PROCESSING</span>
          <h2>Oregon에서 일시 처리</h2>
          <p>업로드한 DXF·STEP·IFC는 미국 Oregon의 Render API로 전송되어 메모리 또는 임시 작업 디렉터리에서 검사됩니다. DatumGuard 애플리케이션은 요청 파일을 서버 프로젝트 저장소나 데이터베이스에 장기 보관하지 않습니다.</p>
          <p>호스팅·네트워크 제공자는 보안과 운영을 위해 IP, 시간, 경로 같은 요청 메타데이터를 각 제공자 정책에 따라 기록할 수 있습니다.</p>
        </article>
        <article>
          <span>02 / BROWSER DRAFTS</span>
          <h2>30일 로컬 draft</h2>
          <p>Architecture, Piping, Plate, Solid 입력 draft는 현재 브라우저의 IndexedDB에만 저장됩니다. 각 저장에는 schema version, 갱신 시각, 30일 만료 시각이 포함되며 만료 후 다음 조회에서 삭제됩니다.</p>
          <p>브라우저 프로필을 공유하는 사람은 이 draft를 볼 수 있습니다. 공용 PC에서는 아래 삭제 기능을 사용하세요.</p>
          <LocalDataControls />
        </article>
        <article>
          <span>03 / NO ACCOUNT</span>
          <h2>이메일·계정 없음</h2>
          <p>공개 데모는 로그인, 이메일 알림, 서버 동기화를 제공하지 않습니다. 결과 파일은 현재 브라우저 세션에서 직접 내려받아야 하며, 탭을 닫은 뒤 서버에서 다시 찾을 수 없습니다.</p>
        </article>
        <article>
          <span>04 / USER CONTROL</span>
          <h2>업로드 전 확인</h2>
          <p>Artifact Lab은 업로드 전에 비기밀 CAD 확인을 요구합니다. 파일 선택만으로는 전송되지 않으며, 사용자가 Audit 또는 Compare 버튼을 누를 때만 API 요청이 시작됩니다.</p>
        </article>
      </section>
    </main>
  );
}
