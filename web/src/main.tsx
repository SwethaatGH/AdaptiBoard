import "@fontsource/atkinson-hyperlegible/400.css";
import "@fontsource/atkinson-hyperlegible/700.css";
import "@fontsource/lexend/400.css";
import "@fontsource/lexend/500.css";
import "@fontsource/lexend/600.css";
import "@fontsource/lexend/700.css";
import React from "react";
import ReactDOM from "react-dom/client";
import Board from "./board/Board";
import Controller from "./controller/Controller";
import "./styles.css";

const isController = location.pathname.startsWith("/controller");
document.title = isController ? "AdaptiBoard · Controller" : "AdaptiBoard";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>{isController ? <Controller /> : <Board />}</React.StrictMode>,
);
