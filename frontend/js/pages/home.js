import { bootSession, ROLE_HOME } from "../api/auth.js";

const user = await bootSession();
if (!user) {
  window.location.replace("/login.html");
} else {
  window.location.replace(ROLE_HOME[user.role] || "/login.html");
}
