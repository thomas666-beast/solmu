import { login } from "./api";

const user = document.getElementById("username") as HTMLInputElement;
const pass = document.getElementById("password") as HTMLInputElement;
const btn = document.getElementById("login-btn") as HTMLButtonElement;
const msg = document.getElementById("msg") as HTMLParagraphElement;

btn.addEventListener("click", async () => {
  msg.textContent = "";
  msg.className = "";
  try {
    await login(user.value, pass.value);
    window.location.href = "/";
  } catch (e) {
    msg.textContent = (e as Error).message;
    msg.className = "line-err";
  }
});
