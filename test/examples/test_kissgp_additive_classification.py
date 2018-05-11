from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

from math import exp

import torch
import unittest
import gpytorch
from torch import optim
from torch.autograd import Variable
from gpytorch.kernels import RBFKernel
from gpytorch.likelihoods import BernoulliLikelihood
from gpytorch.means import ConstantMean
from gpytorch.priors import SmoothedBoxPrior
from gpytorch.random_variables import GaussianRandomVariable

n = 64
train_x = torch.zeros(n ** 2, 2)
train_x[:, 0].copy_(torch.linspace(-1, 1, n).repeat(n))
train_x[:, 1].copy_(torch.linspace(-1, 1, n).unsqueeze(1).repeat(1, n).view(-1))
train_y = train_x[:, 0].abs().lt(0.5).float()
train_y = train_y * (train_x[:, 1].abs().lt(0.5)).float()
train_y = train_y.float() * 2 - 1
train_x = Variable(train_x)
train_y = Variable(train_y)


class GPClassificationModel(gpytorch.models.AdditiveGridInducingVariationalGP):
    def __init__(self):
        super(GPClassificationModel, self).__init__(grid_size=16, grid_bounds=[(-1, 1)], n_components=2)
        self.mean_module = ConstantMean(prior=SmoothedBoxPrior(-1e-5, 1e-5))
        self.covar_module = RBFKernel(
            log_lengthscale_prior=SmoothedBoxPrior(exp(-5), exp(6), sigma=0.1, log_transform=True)
        )
        self.register_parameter(
            name="log_outputscale",
            parameter=torch.nn.Parameter(torch.Tensor([0])),
            prior=SmoothedBoxPrior(exp(-5), exp(6), sigma=0.1, log_transform=True),
        )

    def forward(self, x):
        mean_x = self.mean_module(x)
        covar_x = self.covar_module(x)
        covar_x = covar_x.mul(self.log_outputscale.exp())
        latent_pred = GaussianRandomVariable(mean_x, covar_x)
        return latent_pred


class TestKissGPAdditiveClassification(unittest.TestCase):
    def test_kissgp_classification_error(self):
        with gpytorch.settings.use_toeplitz(False):
            model = GPClassificationModel()
            likelihood = BernoulliLikelihood()
            mll = gpytorch.mlls.VariationalMarginalLogLikelihood(likelihood, model, n_data=len(train_y))

            # Find optimal model hyperparameters
            model.train()
            likelihood.train()

            optimizer = optim.Adam(model.parameters(), lr=0.15)
            optimizer.n_iter = 0
            for _ in range(25):
                optimizer.zero_grad()
                output = model(train_x)
                loss = -mll(output, train_y)
                loss.backward()
                optimizer.n_iter += 1
                optimizer.step()

            for param in model.parameters():
                self.assertTrue(param.grad is not None)
                self.assertGreater(param.grad.norm().item(), 0)
            for param in likelihood.parameters():
                self.assertTrue(param.grad is not None)
                self.assertGreater(param.grad.norm().item(), 0)

            # Set back to eval mode
            model.eval()
            likelihood.eval()

            test_preds = model(train_x).mean().ge(0.5).float().mul(2).sub(1).squeeze()
            mean_abs_error = torch.mean(torch.abs(train_y - test_preds) / 2)

        self.assertLess(mean_abs_error.data.squeeze().item(), 0.15)


if __name__ == "__main__":
    unittest.main()
