import { register } from "./api";

const user = document.getElementById("username") as HTMLInputElement;
const pass = document.getElementById("password") as HTMLInputElement;
const btn = document.getElementById("register-btn") as HTMLButtonElement;
const msg = document.getElementById("msg") as HTMLParagraphElement;

btn.addEventListener("click", async () => {
  msg.textContent = "";
  msg.className = "";
  try {
    await register(user.value, pass.value);
    msg.textContent = "registered — redirecting to login…";
    msg.className = "line-ok";
    setTimeout(() => (window.location.href = "/login"), 800);
  } catch (e) {
    msg.textContent = (e as Error).message;
    msg.className = "line-err";
  }
});
