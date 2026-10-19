import { directionKey, directionLabel } from "../utils/format";
import "../styles/LineItemName.css";

/* Whether a saved line item is a debit (money out, red) or a credit (money in,
   green). Takes the server's direction, "in"/"out" or "credit"/"debit". */
const DirectionBadge = ({ direction }) => (
  <span className={`direction-badge is-${directionKey(direction)}`}>{directionLabel(direction)}</span>
);

export default DirectionBadge;
