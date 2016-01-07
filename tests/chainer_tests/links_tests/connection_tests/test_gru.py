import unittest

import numpy

import chainer
from chainer import cuda
from chainer import gradient_check
from chainer import links
from chainer import testing
from chainer.testing import attr


def _sigmoid(x):
    xp = cuda.get_array_module(x)
    return 1 / (1 + xp.exp(-x))


def _gru(func, h, x):
    xp = cuda.get_array_module(h, x)

    r = _sigmoid(x.dot(func.W_r.W.data.T) + h.dot(func.U_r.W.data.T))
    z = _sigmoid(x.dot(func.W_z.W.data.T) + h.dot(func.U_z.W.data.T))
    h_bar = xp.tanh(x.dot(func.W.W.data.T) + (r * h).dot(func.U.W.data.T))
    y = (1 - z) * h + z * h_bar
    return y


@testing.parameterize(
    {'gru': links.GRU},
    {'gru': links.StatefulGRU}
)
class TestStatefulGRU(unittest.TestCase):

    def setUp(self):
        self.link = self.gru(8)
        self.x = numpy.random.uniform(-1, 1, (3, 8)).astype(numpy.float32)
        self.h = numpy.random.uniform(-1, 1, (3, 8)).astype(numpy.float32)
        self.gy = numpy.random.uniform(-1, 1, (3, 8)).astype(numpy.float32)

    def _forward(self, link, h, x):
        if isinstance(link, links.GRU):
            return link(h, x)
        else:
            link.set_state(h.data)
            return link(x)

    def check_forward(self, h_data, x_data):
        h = chainer.Variable(h_data)
        x = chainer.Variable(x_data)
        y = self._forward(self.link, h, x)

        self.assertEqual(y.data.dtype, numpy.float32)
        y_expect = _gru(self.link, h_data, x_data)
        gradient_check.assert_allclose(y_expect, y.data)
        if isinstance(self.link, links.StatefulGRU):
            gradient_check.assert_allclose(self.link.h.data, y.data)

    def test_forward_cpu(self):
        self.check_forward(self.h, self.x)

    @attr.gpu
    def test_forward_gpu(self):
        self.link.to_gpu()
        self.check_forward(cuda.to_gpu(self.h),
                           cuda.to_gpu(self.x))

    def check_backward(self, h_data, x_data, y_grad):
        h = chainer.Variable(h_data)
        x = chainer.Variable(x_data)
        y = self._forward(self.link, h, x)
        y.grad = y_grad
        y.backward()

        f = lambda: (_gru(self.link, h_data, x_data),)
        gx, = gradient_check.numerical_grad(f, (x.data,), (y.grad,))
        gradient_check.assert_allclose(gx, x.grad, atol=1e-3)

        if isinstance(self.link, links.GRU):
            gh, = gradient_check.numerical_grad(f, (h.data,), (y.grad,))
            gradient_check.assert_allclose(gh, h.grad, atol=1e-3)

    def test_backward_cpu(self):
        self.check_backward(self.h, self.x, self.gy)

    @attr.gpu
    def test_backward_gpu(self):
        self.link.to_gpu()
        self.check_backward(cuda.to_gpu(self.h),
                            cuda.to_gpu(self.x),
                            cuda.to_gpu(self.gy))


@testing.parameterize(
    *testing.product({
        'link_array_module': ['to_cpu', 'to_gpu'],
        'state_array_module': ['to_cpu', 'to_gpu']
    }))
class TestGRUState(unittest.TestCase):

    def setUp(self):
        self.link = links.StatefulGRU(8)
        self.h = numpy.random.uniform(-1, 1, (3, 8)).astype(numpy.float32)

    def check_set_state(self, h):
        self.link.set_state(h)
        self.assertIsInstance(self.link.h.data, self.link.xp.ndarray)

    def test_set_state_cpu(self):
        self.check_set_state(self.h)

    @attr.gpu
    def test_set_state_gpu(self):
        getattr(self.link, self.link_array_module)()
        h = getattr(chainer.cuda, self.state_array_module)(self.h)
        self.check_set_state(h)

    def check_reset_state(self):
        self.link.reset_state()
        self.assertIsNone(self.link.h)

    def test_reset_state_cpu(self):
        self.check_reset_state()

    @attr.gpu
    def test_reset_state_gpu(self):
        getattr(self.link, self.link_array_module)()
        self.check_reset_state()


class TestGRUToCPUToGPU(unittest.TestCase):

    def setUp(self):
        self.link = links.StatefulGRU(8)
        self.h = numpy.random.uniform(-1, 1, (3, 8)).astype(numpy.float32)

    def check_to_cpu(self, h):
        self.link.set_state(h)
        self.link.to_cpu()
        self.assertIsInstance(self.link.h.data, self.link.xp.ndarray)
        self.link.to_cpu()
        self.assertIsInstance(self.link.h.data, self.link.xp.ndarray)

    def test_to_cpu_cpu(self):
        self.check_to_cpu(self.h)

    @attr.gpu
    def test_to_cpu_gpu(self):
        self.check_to_cpu(chainer.cuda.to_gpu(self.h))

    def check_to_cpu_to_gpu(self, h):
        self.link.set_state(h)
        self.link.to_gpu()
        self.assertIsInstance(self.link.h.data, self.link.xp.ndarray)
        self.link.to_gpu()
        self.assertIsInstance(self.link.h.data, self.link.xp.ndarray)
        self.link.to_cpu()
        self.assertIsInstance(self.link.h.data, self.link.xp.ndarray)
        self.link.to_gpu()
        self.assertIsInstance(self.link.h.data, self.link.xp.ndarray)

    @attr.gpu
    def test_to_cpu_to_gpu_cpu(self):
        self.check_to_cpu_to_gpu(self.h)

    @attr.gpu
    def test_to_cpu_to_gpu_gpu(self):
        self.check_to_cpu_to_gpu(chainer.cuda.to_gpu(self.h))


testing.run_module(__name__, __file__)
