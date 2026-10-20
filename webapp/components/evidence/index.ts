// index.ts -- the evidence kit's public surface. Every page renders a number, its as-of
// date, its source path and its verdict label through these, never ad hoc.
export { AsOfBadge, asOfText } from "./AsOfBadge";
export { FigureValue, figureText, figureReceipt } from "./FigureValue";
export { NotClaimed, NOT_CLAIMED_LINES } from "./NotClaimed";
export { ReceiptChip, receiptText, type ReceiptChipProps } from "./ReceiptChip";
export { Term } from "./Term";
export { GLOSSARY, GLOSSARY_IDS, type GlossaryId } from "./glossary";
export {
  VerdictLabel, PACKET_VERDICTS, VERDICT_QUALIFIER, VERDICT_MEANING,
  isPacketVerdict, toPacketVerdict, verdictQualifier, type PacketVerdict,
} from "./VerdictLabel";
export { PACKET_HREF, PACKET_PATH, blobUrl, receiptHref, isRepoPath, type ReceiptStatus } from "./kit";
