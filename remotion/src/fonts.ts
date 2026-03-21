import { staticFile } from "remotion";

// Inject @font-face via style element — works reliably in Remotion's headless Chromium
const style = document.createElement("style");
style.textContent = `
@font-face {
  font-family: 'Pretendard';
  src: url('${staticFile("fonts/PretendardVariable.woff2")}') format('woff2');
  font-weight: 100 900;
  font-style: normal;
  font-display: swap;
}
`;
document.head.appendChild(style);
