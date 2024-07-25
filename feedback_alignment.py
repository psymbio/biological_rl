import torch
import torch.nn as nn
from torch.autograd import Function

class FeedbackAlignmentFunction(Function):
    @staticmethod
    def forward(ctx, input, *params):
        num_layers = len(params) // 3
        weights = params[:num_layers]
        biases = params[num_layers:2*num_layers]
        feedback_matrices = params[2*num_layers:3*num_layers]

        activations = [input]
        z_values = []

        for i in range(len(weights)):
            z = input.matmul(weights[i].t()) + biases[i]
            z_values.append(z)
            input = torch.relu(z) if i < len(weights) - 1 else z
            activations.append(input)

        ctx.save_for_backward(*weights, *biases, *feedback_matrices, *z_values, *activations)
        ctx.num_layers = len(weights)
        return input

    @staticmethod
    def backward(ctx, grad_output):
        # print("FeedbackAlignmentFunction: Backward function called")
        saved_tensors = ctx.saved_tensors
        num_layers = ctx.num_layers

        weights = saved_tensors[:num_layers]
        biases = saved_tensors[num_layers:2*num_layers]
        feedback_matrices = saved_tensors[2*num_layers:3*num_layers]
        z_values = saved_tensors[3*num_layers:4*num_layers]
        activations = saved_tensors[4*num_layers:]

        delta = grad_output

        grad_weights = [None] * num_layers
        grad_biases = [None] * num_layers
        grad_feedback_matrices = [None] * len(feedback_matrices)

        for i in reversed(range(num_layers)):
            grad_weights[i] = delta.t().matmul(activations[i])
            grad_biases[i] = delta.sum(0)

            if i > 0:
                delta = delta.matmul(feedback_matrices[i]) * (z_values[i-1] > 0).float()  # ReLU derivative

        grad_weights = [g.contiguous() if g is not None else None for g in grad_weights]
        grad_biases = [g.contiguous() if g is not None else None for g in grad_biases]


        return None, *grad_weights, *grad_biases, *grad_feedback_matrices


class FeedbackAlignmentMLP(nn.Module):
    def __init__(self, input_size, hidden_sizes, output_size):
        super(FeedbackAlignmentMLP, self).__init__()
        self.weights = nn.ParameterList()
        self.biases = nn.ParameterList()
        self.feedback_matrices = nn.ParameterList()

        prev_size = input_size
        for hidden_size in hidden_sizes:
            self.weights.append(nn.Parameter(torch.Tensor(hidden_size, prev_size), requires_grad=True))
            self.biases.append(nn.Parameter(torch.Tensor(hidden_size), requires_grad=True))
            self.feedback_matrices.append(nn.Parameter(torch.randn(hidden_size, prev_size), requires_grad=False))
            prev_size = hidden_size

        self.weights.append(nn.Parameter(torch.Tensor(output_size, prev_size), requires_grad=True))
        self.biases.append(nn.Parameter(torch.Tensor(output_size), requires_grad=True))
        self.feedback_matrices.append(nn.Parameter(torch.randn(output_size, hidden_sizes[-1]), requires_grad=False))

        self.reset_parameters()

    def reset_parameters(self):
        for weight in self.weights:
            nn.init.kaiming_uniform_(weight, a=5**0.5)
        for bias in self.biases:
            nn.init.constant_(bias, 0)

    def forward(self, input):

        return FeedbackAlignmentFunction.apply(input, *self.weights, *self.biases, *self.feedback_matrices)
