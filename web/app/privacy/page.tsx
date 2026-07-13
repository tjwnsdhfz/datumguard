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
        <p>DatumGuard 공개 데모는 계정이나 장기 프로젝트 저장소가 아닙니다. 페이지뷰 분석도 설계 데이터를 수집하도록 구성하지 않았습니다. 고객 기밀, 개인정보, 수출통제, 의료·방산·규제 대상 파일은 업로드하지 마세요.</p>
      </section>
      <section className="privacy-grid">
        <article>
          <span>01 / SERVER PROCESSING</span>
          <h2>Oregon에서 일시 처리</h2>
          <p>업로드한 DXF·STEP·IFC·IDS는 활성화된 API로 전송되어 메모리 또는 임시 작업 디렉터리에서 검사됩니다. 현재 공개 v0.4.0은 미국 Oregon의 Render API를 사용하며, OpenBIM은 공개 UI와 동결 evidence만 제공하고 hosted 실행은 비활성입니다. 로컬 또는 별도 연결 환경에서 OpenBIM 실행을 켜도 같은 stateless 처리 경계를 따릅니다. DatumGuard 애플리케이션은 요청 파일을 서버 프로젝트 저장소나 데이터베이스에 장기 보관하지 않습니다.</p>
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
          <p>Artifact Lab과 OpenBIM workspace는 업로드 전에 비기밀 파일 확인을 요구합니다. 파일 선택만으로는 전송되지 않으며, 사용자가 Audit, Compare 또는 OpenBIM evidence 실행 버튼을 누를 때만 API 요청이 시작됩니다.</p>
        </article>
        <article>
          <span>05 / PAGEVIEW ANALYTICS</span>
          <h2>페이지뷰 기준선만 측정</h2>
          <p>현재 공개 웹은 Vercel Web Analytics로 페이지 방문 수준의 기준선만 확인합니다. DatumGuard는 custom event를 보내지 않으며, 분석용 cookie를 설정하지 않습니다. 설계 payload, 파일명, contract 또는 artifact hash, 좌표, 치수, 검증 오류 내용은 분석 항목에 넣지 않습니다.</p>
          <p>다만 페이지뷰 요청도 네트워크를 통과하므로 Vercel과 네트워크 제공자는 URL, referrer, IP address, user agent, 시간 같은 요청·브라우저 메타데이터를 각자의 정책에 따라 처리할 수 있습니다. “DatumGuard 애플리케이션 데이터베이스에 저장하지 않는다”는 설명은 제공자 측 보안 로그나 운영 처리가 전혀 없다는 보장이 아닙니다.</p>
        </article>
        <article>
          <span>06 / CONTROL &amp; RETENTION</span>
          <h2>앱 내 분석 opt-out은 없음</h2>
          <p>현재 DatumGuard에는 Web Analytics를 끄는 별도 앱 내 설정이 없습니다. 브라우저 또는 네트워크의 콘텐츠 차단 기능은 사용자가 직접 선택할 수 있지만, 모든 차단 동작을 보장하지는 않습니다.</p>
          <p>브라우저 draft의 30일 만료와 분석 보고 기간은 서로 다른 정책입니다. draft는 위 IndexedDB 규칙으로 관리되고, 분석 dashboard의 보고 기간과 제공자 운영 로그의 보존은 Vercel 요금제·제품 설정·정책에 따릅니다. DatumGuard는 이 보고 데이터를 설계 계약, API 요청 또는 산출물과 결합하지 않습니다.</p>
        </article>
      </section>
    </main>
  );
}
