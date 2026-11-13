import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import ModelSelector from '../components/ModelSelector';

describe('ModelSelector', () => {
  it('renders only the models supplied by the component', () => {
    render(<ModelSelector />);

    expect(screen.getByRole('heading', { name: 'Select Model' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /GPT-4/ })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Claude-3/ })).toBeInTheDocument();
    expect(screen.queryByText('DialoGPT Medium')).not.toBeInTheDocument();
  });

  it('passes the complete selected model to the callback', () => {
    const onSelect = vi.fn();
    render(<ModelSelector onSelect={onSelect} />);

    fireEvent.click(screen.getByRole('button', { name: /Claude-3/ }));

    expect(onSelect).toHaveBeenCalledExactlyOnceWith({
      id: '2',
      name: 'Claude-3',
      provider: 'Anthropic',
      version: '3.0',
      description: 'Constitutional AI model',
    });
  });

  it('marks the selected model and clears the previous selection', () => {
    render(<ModelSelector />);
    const gptButton = screen.getByRole('button', { name: /GPT-4/ });
    const claudeButton = screen.getByRole('button', { name: /Claude-3/ });

    fireEvent.click(gptButton);
    expect(gptButton).toHaveClass('border-blue-500');

    fireEvent.click(claudeButton);
    expect(claudeButton).toHaveClass('border-blue-500');
    expect(gptButton).toHaveClass('border-slate-200');
  });

  it('keeps model cards keyboard-focusable native buttons', () => {
    render(<ModelSelector />);
    const button = screen.getByRole('button', { name: /GPT-4/ });

    button.focus();
    expect(button).toHaveFocus();
    expect(button.tagName).toBe('BUTTON');
  });

  it('does not require a callback to render or select a model', () => {
    render(<ModelSelector />);

    expect(() => fireEvent.click(screen.getByRole('button', { name: /GPT-4/ }))).not.toThrow();
  });
});
