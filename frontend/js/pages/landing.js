import { bootSession, ROLE_HOME } from "../api/auth.js";

// Progressive enhancement: the marketing landing is fully public and static.
// If a session is already active (refresh cookie), point the CTAs at the
// signed-in user's dashboard instead of the login page.
const user = await bootSession();
if (user) {
  const home = ROLE_HOME[user.role] || "/";
  const signin = document.getElementById("cta-signin");
  if (signin) {
    signin.href = home;
    signin.textContent = "Go to dashboard";
  }
  for (const id of ["cta-book", "cta-book-2"]) {
    const link = document.getElementById(id);
    if (link) link.href = home;
  }
}
