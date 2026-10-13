import {cookies} from 'next/headers';
import {redirect} from 'next/navigation';
import {ACCESS_COOKIE, accessConfigured, verifyAccessToken} from '../lib/server/access';
import styles from './access.module.css';

export default async function AccessPage({searchParams}:{searchParams:Promise<{error?:string}>}) {
  const tokens=(await cookies()).getAll(ACCESS_COOKIE);
  if(tokens.length===1 && verifyAccessToken(tokens[0].value))redirect('/');
  const configured=accessConfigured();
  const {error}=await searchParams;
  return <main className={styles.shell}>
    <section className={styles.panel} aria-labelledby="access-title">
      <p className={styles.eyebrow}>TRUE OR NOT</p>
      <h1 id="access-title">접속 비밀번호</h1>
      <p className={styles.description}>공유받은 비밀번호를 입력해 워크스페이스에 접속하세요.</p>
      {!configured ? <p role="alert" className={styles.error}>서비스 접속이 준비되지 않았습니다. 관리자에게 문의해 주세요.</p> : <form action="/api/access/login" method="post" className={styles.form}>
        <label htmlFor="access-password">비밀번호</label>
        <input id="access-password" name="password" type="password" autoComplete="current-password" required maxLength={256} aria-describedby={error==='invalid'?'access-error':undefined}/>
        {error==='invalid' && <p id="access-error" role="alert" className={styles.error}>비밀번호를 확인하고 다시 입력해 주세요.</p>}
        <button type="submit">입장하기</button>
      </form>}
      <p className={styles.note}>접속은 24시간 유지됩니다. 공용 기기에서는 이용 후 로그아웃해 주세요.</p>
      <div className={styles.links}><a href="/privacy">개인정보 처리방침</a><a href="/terms">이용약관</a></div>
    </section>
  </main>;
}
