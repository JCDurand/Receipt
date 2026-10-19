import React from "react";
import { formatMoney } from "../utils/format";
import { toCents } from "../utils/spending";

/* "ZAR -> USD" beside a line item which was converted from the currency it was
   recorded in, with the original amount and the rate used on hover. Says so
   when there was no rate to convert with. Nothing for a line which was not converted. */
const ConversionBadge = ({ line }) => {
  if (!line?.conversion) return null;
  const original = formatMoney(Math.abs(toCents(line.original_amount)), { currency: line.original_currency });
  const title = line.rate_unavailable
    ? `No exchange rate was available, so this is shown as recorded: ${original}`
    : `Recorded as ${original}, converted at ${Number(line.exchange_rate).toFixed(4)} (the rate on its date)`;
  return (
    <span className={`conversion-badge${line.rate_unavailable ? " is-missing" : ""}`} title={title}>
      {line.conversion}
    </span>
  );
};

export default ConversionBadge;
