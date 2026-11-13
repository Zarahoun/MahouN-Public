import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import LandingPage from '../pages/LandingPage';

describe('LandingPage accessibility structure', () => {
  it('provides main and footer landmarks with a coherent heading hierarchy', () => {
    const { container } = render(
      <MemoryRouter>
        <LandingPage />
      </MemoryRouter>
    );

    expect(screen.getAllByRole('main')).toHaveLength(1);
    expect(screen.getByRole('contentinfo')).toBeInTheDocument();

    const headingLevels = Array.from(container.querySelectorAll('h1, h2, h3, h4, h5, h6')).map(
      (heading) => Number(heading.tagName.slice(1))
    );
    expect(headingLevels[0]).toBe(1);
    expect(headingLevels.slice(1).every((level, index) => level <= headingLevels[index] + 1)).toBe(
      true
    );
  });
});
