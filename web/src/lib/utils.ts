export { cn } from "cn"

// Documents skipped on the review screen in this tab, so the review queue does not keep opening the same one.
const SKIPPED = "crosscheck-skipped"
export const skippedIds = (): number[] => JSON.parse(sessionStorage.getItem(SKIPPED) ?? "[]")
export const skip = (id: number) => sessionStorage.setItem(SKIPPED, JSON.stringify([...new Set([...skippedIds(), id])]))
export const clearSkipped = () => sessionStorage.removeItem(SKIPPED)
