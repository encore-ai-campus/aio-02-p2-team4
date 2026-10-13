import FactCheckDashboard from "./components/fact-check-dashboard";
import {cookies} from 'next/headers';
import {redirect} from 'next/navigation';
import {ACCESS_COOKIE, accessEnabled, verifyAccessToken} from './lib/server/access';
import styles from './access/access.module.css';

export default async function Home() {
  const protectedSite=accessEnabled();
  if(protectedSite) {
    const tokens=(await cookies()).getAll(ACCESS_COOKIE);
    if(tokens.length!==1 || !verifyAccessToken(tokens[0].value))redirect('/access');
  }
  return <>{protectedSite && <form action="/api/access/logout" method="post" className={styles.logout}><button type="submit">로그아웃</button></form>}<FactCheckDashboard /></>;
}
