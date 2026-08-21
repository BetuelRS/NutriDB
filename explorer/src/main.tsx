import { createRoot } from "react-dom/client";
import App from "./AtlasApp";

const root = document.getElementById("root");
if (root === null) throw new Error("root element missing");
createRoot(root).render(<App />);
