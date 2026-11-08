import { motion } from "framer-motion";
import { BellRing, Siren } from "lucide-react";
import type { Alert } from "../lib/types";

/**
 * Full-screen alert after an emergency / urgent Need. The board keeps speaking the
 * sentence (see Board.tsx). OK on the remote, or a click, cancels it - but only
 * after a few seconds so the same gaze that triggered it can't cancel it.
 */
export function AlertOverlay({ alert, armed, notified, onClose }: { alert: Alert; armed: boolean; notified: boolean; onClose: () => void }) {
  const emergency = alert.level === "emergency";
  return (
    <motion.div
      className={`alert-overlay ${emergency ? "is-emergency" : "is-urgent"}`}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <motion.div className="alert-card" initial={{ scale: 0.92, y: 20 }} animate={{ scale: 1, y: 0 }}>
        <div className="alert-icon">{emergency ? <Siren size={56} /> : <BellRing size={52} />}</div>
        <small>{emergency ? "Emergency" : "Needs help"}</small>
        <h1>{emergency ? "Call 911" : alert.label}</h1>
        <p className="alert-what">{emergency ? alert.label : ""}</p>
        <p className="alert-say">“{alert.say}”</p>
        <p className="alert-note">
          {notified ? "Caregiver's phone has been notified. " : ""}
          AdaptiBoard does not dial 911 itself: someone nearby must call.
        </p>
        <button type="button" className={`alert-close ${armed ? "" : "is-waiting"}`} onClick={onClose}>
          {armed ? "OK · I'm okay now / help is here" : "Alerting…"}
        </button>
      </motion.div>
    </motion.div>
  );
}
