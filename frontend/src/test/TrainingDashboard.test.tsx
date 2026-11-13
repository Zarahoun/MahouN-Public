import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import TrainingDashboard from '../components/TrainingDashboard';

const { listAvailableModels } = vi.hoisted(() => ({
  listAvailableModels: vi.fn(),
}));

vi.mock('../api/trainingClient', () => ({ listAvailableModels }));

const models = {
  models: [
    {
      id: 'legal-model-1',
      name: 'مدل حقوقی',
      provider: 'local',
      size: '8B',
      capabilities: ['reasoning'],
      description: 'مدل استدلال حقوقی',
    },
  ],
};

function fillRequiredFields() {
  fireEvent.change(screen.getByPlaceholderText('نام dataset را وارد کنید...'), {
    target: { value: 'legal-cases' },
  });
  fireEvent.change(screen.getByPlaceholderText('نام اجرا را وارد کنید...'), {
    target: { value: 'baseline-run' },
  });
}

function submitForm() {
  fireEvent.submit(screen.getByRole('button', { name: 'شروع آموزش' }).closest('form')!);
}

describe('TrainingDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    listAvailableModels.mockResolvedValue(models);
  });

  it('keeps the loading state visible until the models request resolves', async () => {
    let resolveModels!: (value: typeof models) => void;
    listAvailableModels.mockReturnValue(
      new Promise<typeof models>((resolve) => {
        resolveModels = resolve;
      })
    );

    render(<TrainingDashboard onStartTraining={vi.fn()} />);
    expect(screen.getByRole('heading', { name: 'آموزش مدل' })).toBeInTheDocument();
    expect(screen.queryByLabelText('انتخاب مدل')).not.toBeInTheDocument();

    resolveModels(models);
    expect(await screen.findByLabelText('انتخاب مدل')).toBeInTheDocument();
  });

  it('populates the model selector only with models returned by the API', async () => {
    render(<TrainingDashboard onStartTraining={vi.fn()} />);

    const selector = await screen.findByLabelText('انتخاب مدل');
    expect(selector).toHaveValue('');
    expect(screen.getByRole('option', { name: /مدل حقوقی/ })).toHaveValue('legal-model-1');
    expect(screen.queryByText('DialoGPT Medium')).not.toBeInTheDocument();
  });

  it('keeps the form available when required model validation fails', async () => {
    render(<TrainingDashboard onStartTraining={vi.fn()} />);
    await screen.findByLabelText('انتخاب مدل');
    fillRequiredFields();

    submitForm();

    expect(await screen.findByRole('alert')).toHaveTextContent('لطفاً یک مدل را انتخاب کنید');
    expect(screen.getByLabelText('انتخاب مدل')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('نام اجرا را وارد کنید...')).toBeInTheDocument();
  });

  it('submits the selected model and configured numeric values without coercion errors', async () => {
    const onStartTraining = vi.fn();
    render(<TrainingDashboard onStartTraining={onStartTraining} />);
    await screen.findByLabelText('انتخاب مدل');

    fireEvent.change(screen.getByLabelText('انتخاب مدل'), {
      target: { value: 'legal-model-1' },
    });
    fillRequiredFields();
    fireEvent.change(screen.getByLabelText('تعداد epochs'), { target: { value: '5' } });
    fireEvent.change(screen.getByLabelText('Batch size (train)'), {
      target: { value: '8' },
    });
    fireEvent.change(screen.getByLabelText('Learning rate'), {
      target: { value: '0.0001' },
    });

    submitForm();

    await waitFor(() => {
      expect(onStartTraining).toHaveBeenCalledExactlyOnceWith({
        model_name: 'legal-model-1',
        training_mode: 'lora',
        num_train_epochs: 5,
        batch_size: 8,
        learning_rate: 0.0001,
        dataset_name: 'legal-cases',
        run_name: 'baseline-run',
        quantization: null,
      });
    });
  });

  it('shows quantization only for QLoRA and includes it in the submitted configuration', async () => {
    const onStartTraining = vi.fn();
    render(<TrainingDashboard onStartTraining={onStartTraining} />);
    await screen.findByLabelText('انتخاب مدل');

    fireEvent.change(screen.getByLabelText('انتخاب مدل'), {
      target: { value: 'legal-model-1' },
    });
    expect(screen.queryByRole('radio', { name: 'INT4' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', { name: 'QLoRA' }));
    fireEvent.click(screen.getByRole('radio', { name: 'INT4' }));
    fillRequiredFields();
    submitForm();

    await waitFor(() => {
      expect(onStartTraining).toHaveBeenCalledWith(
        expect.objectContaining({ training_mode: 'qlora', quantization: 'INT4' })
      );
    });
  });

  it('disables submission while a training request is active', async () => {
    render(<TrainingDashboard onStartTraining={vi.fn()} isTraining />);
    await screen.findByLabelText('انتخاب مدل');

    expect(screen.getByRole('button', { name: 'در حال آموزش...' })).toBeDisabled();
  });

  it('exposes model-loading errors and recovers after retry', async () => {
    listAvailableModels.mockRejectedValueOnce(new Error('models unavailable'));
    render(<TrainingDashboard onStartTraining={vi.fn()} />);

    expect(await screen.findByText('models unavailable')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'تلاش مجدد' }));

    expect(await screen.findByLabelText('انتخاب مدل')).toBeInTheDocument();
    expect(listAvailableModels).toHaveBeenCalledTimes(2);
    expect(screen.queryByText('models unavailable')).not.toBeInTheDocument();
  });
});
