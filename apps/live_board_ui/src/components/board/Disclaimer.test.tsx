// Honesty guard for Disclaimer -- locks the binding copy so a future edit
// cannot silently introduce edge language or remove the honest disclaimer.
import { render, screen } from "@testing-library/react"
import { describe, it, expect } from "vitest"
import { Disclaimer } from "@/components/board/Disclaimer"

describe("Disclaimer -- honesty invariants", () => {
  describe('variant="banner"', () => {
    it("renders the binding no-edge text", () => {
      render(<Disclaimer variant="banner" />)
      expect(
        screen.getByText(/no \$ edge claimed/i)
      ).toBeInTheDocument()
    })

    it("renders market-implied language", () => {
      render(<Disclaimer variant="banner" />)
      expect(
        screen.getByText(/market-implied/i)
      ).toBeInTheDocument()
    })

    it("NEGATIVE: contains no edge-claim language", () => {
      const { container } = render(<Disclaimer variant="banner" />)
      const text = container.textContent ?? ""
      expect(text).not.toMatch(/beat the market|\+EV|guaranteed|profit/i)
    })
  })

  describe('variant="footer" (explicit)', () => {
    it("renders the binding no-edge text", () => {
      render(<Disclaimer variant="footer" />)
      expect(
        screen.getByText(/no \$ edge claimed/i)
      ).toBeInTheDocument()
    })

    it("NEGATIVE: contains no edge-claim language", () => {
      const { container } = render(<Disclaimer variant="footer" />)
      const text = container.textContent ?? ""
      expect(text).not.toMatch(/beat the market|\+EV|guaranteed|profit/i)
    })
  })

  describe("default variant (omitted prop)", () => {
    it("renders the binding no-edge text", () => {
      render(<Disclaimer />)
      expect(
        screen.getByText(/no \$ edge claimed/i)
      ).toBeInTheDocument()
    })

    it("NEGATIVE: contains no edge-claim language", () => {
      const { container } = render(<Disclaimer />)
      const text = container.textContent ?? ""
      expect(text).not.toMatch(/beat the market|\+EV|guaranteed|profit/i)
    })
  })
})
