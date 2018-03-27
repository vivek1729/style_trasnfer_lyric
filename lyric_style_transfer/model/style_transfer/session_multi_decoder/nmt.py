'''
Build a simple neural machine translation model
'''
import theano
import theano.tensor as tensor
from theano.sandbox.rng_mrg import MRG_RandomStreams as RandomStreams

import cPickle as pkl
import ipdb
import numpy
import copy

import os
import warnings
import sys
import time

from collections import OrderedDict

from data_iterator import TextIterator

profile = False



# push parameters to Theano shared variables
def zipp(params, tparams):
    for kk, vv in params.iteritems():
        tparams[kk].set_value(vv)


# pull parameters from Theano shared variables
def unzip(zipped):
    new_params = OrderedDict()
    for kk, vv in zipped.iteritems():
        new_params[kk] = vv.get_value()
    return new_params


# get the list of parameters: Note that tparams must be OrderedDict
def itemlist(tparams):
    return [vv for kk, vv in tparams.iteritems()]


# dropout
def dropout_layer(state_before, use_noise, trng):
    proj = tensor.switch(
        use_noise,
        state_before * trng.binomial(state_before.shape, p=0.5, n=1,
                                     dtype=state_before.dtype),
        state_before * 0.5)
    return proj


# make prefix-appended name
def _p(pp, name):
    return '%s_%s' % (pp, name)


# initialize Theano shared variables according to the initial parameters
def init_tparams(params):
    tparams = OrderedDict()
    for kk, pp in params.iteritems():
        tparams[kk] = theano.shared(params[kk], name=kk)
    return tparams


# load parameters
def load_params(path, params):
    pp = numpy.load(path)
    for kk, vv in params.iteritems():
        if kk not in pp:
            warnings.warn('%s is not in the archive' % kk)
            continue
        params[kk] = pp[kk]

    return params

# layers: 'name': ('parameter initializer', 'feedforward')
layers = {'ff': ('param_init_fflayer', 'fflayer'),
          'gru': ('param_init_gru', 'gru_layer'),
          'gru_cond_simple': ('param_init_gru_cond_simple',
                              'gru_cond_simple_layer'),
          'gru_cond_attention':('param_init_gru_cond_attention',
                              'gru_cond_attention_layer')
          }


def get_layer(name):
    fns = layers[name]
    return (eval(fns[0]), eval(fns[1]))


# some utilities
def ortho_weight(ndim):
    W = numpy.random.randn(ndim, ndim)
    u, s, v = numpy.linalg.svd(W)
    return u.astype('float32')


def norm_weight(nin, nout=None, scale=0.01, ortho=True):
    if nout is None:
        nout = nin
    if nout == nin and ortho:
        W = ortho_weight(nin)
    else:
        W = scale * numpy.random.randn(nin, nout)
    return W.astype('float32')


def tanh(x):
    return tensor.tanh(x)


def linear(x):
    return x


def concatenate(tensor_list, axis=0):
    """
    Alternative implementation of `theano.tensor.concatenate`.
    This function does exactly the same thing, but contrary to Theano's own
    implementation, the gradient is implemented on the GPU.
    Backpropagating through `theano.tensor.concatenate` yields slowdowns
    because the inverse operation (splitting) needs to be done on the CPU.
    This implementation does not have that problem.
    :usage:
        >>> x, y = theano.tensor.matrices('x', 'y')
        >>> c = concatenate([x, y], axis=1)
    :parameters:
        - tensor_list : list
            list of Theano tensor expressions that should be concatenated.
        - axis : int
            the tensors will be joined along this axis.
    :returns:
        - out : tensor
            the concatenated tensor expression.
    """
    concat_size = sum(tt.shape[axis] for tt in tensor_list)

    output_shape = ()
    for k in range(axis):
        output_shape += (tensor_list[0].shape[k],)
    output_shape += (concat_size,)
    for k in range(axis + 1, tensor_list[0].ndim):
        output_shape += (tensor_list[0].shape[k],)

    out = tensor.zeros(output_shape)
    offset = 0
    for tt in tensor_list:
        indices = ()
        for k in range(axis):
            indices += (slice(None),)
        indices += (slice(offset, offset + tt.shape[axis]),)
        for k in range(axis + 1, tensor_list[0].ndim):
            indices += (slice(None),)

        out = tensor.set_subtensor(out[indices], tt)
        offset += tt.shape[axis]

    return out


# batch preparation, returns padded batches for both source and target
# sequences with their corresponding masks
def prepare_data(seqs_x, seqs_y, senti, maxlen=None,
                 n_words_src=30000, n_words=30000):

    # x: a list of sentences
    lengths_x = [len(s) for s in seqs_x]
    lengths_y = [len(s) for s in seqs_y]

    # filter sequences according to maximum sequence length
    if maxlen is not None:
        new_seqs_x = []
        new_seqs_y = []
        new_senti = []
        new_lengths_x = []
        new_lengths_y = []
        for l_x, s_x, l_y, s_y, s_t in zip(lengths_x, seqs_x, lengths_y, seqs_y, senti):
            if l_x < maxlen and l_y < maxlen:
                new_seqs_x.append(s_x)
                new_lengths_x.append(l_x)
                new_seqs_y.append(s_y)
                new_lengths_y.append(l_y)
                new_senti.append(s_t)
        lengths_x = new_lengths_x
        seqs_x = new_seqs_x
        lengths_y = new_lengths_y
        seqs_y = new_seqs_y
        senti = new_senti

        if len(lengths_x) < 1 or len(lengths_y) < 1:
            return None, None, None, None, None

    n_samples = len(seqs_x)
    maxlen_x = numpy.max(lengths_x) + 1
    maxlen_y = numpy.max(lengths_y) + 1

    senti = numpy.array(senti).astype('int32')

    # pad batches and create masks
    x = numpy.zeros((maxlen_x, n_samples)).astype('int64')
    y = numpy.zeros((maxlen_y, n_samples)).astype('int64')
    x_mask = numpy.zeros((maxlen_x, n_samples)).astype('float32')
    y_mask = numpy.zeros((maxlen_y, n_samples)).astype('float32')
    for idx, [s_x, s_y] in enumerate(zip(seqs_x, seqs_y)):
        x[:lengths_x[idx], idx] = s_x
        x_mask[:lengths_x[idx]+1, idx] = 1.
        y[:lengths_y[idx], idx] = s_y
        y_mask[:lengths_y[idx]+1, idx] = 1.

    return x, x_mask, y, y_mask, senti


# feedforward layer: affine transformation + point-wise nonlinearity
def param_init_fflayer(options, params, prefix='ff', nin=None, nout=None,
                       ortho=True):
    if nin is None:
        nin = options['dim_proj']
    if nout is None:
        nout = options['dim_proj']
    params[_p(prefix, 'W')] = norm_weight(nin, nout, scale=0.01, ortho=ortho)
    params[_p(prefix, 'b')] = numpy.zeros((nout,)).astype('float32')

    return params


def fflayer(tparams, state_below, options, prefix='rconv',
            activ='lambda x: tensor.tanh(x)', **kwargs):
    return eval(activ)(
        tensor.dot(state_below, tparams[_p(prefix, 'W')]) +
        tparams[_p(prefix, 'b')])


# GRU layer
def param_init_gru(options, params, prefix='gru', nin=None, dim=None):

    if nin is None:
        nin = options['dim_proj']
    if dim is None:
        dim = options['dim_proj']

    # embedding to gates transformation weights, biases
    W = numpy.concatenate([norm_weight(nin, dim),
                           norm_weight(nin, dim)], axis=1)
    params[_p(prefix, 'W')] = W
    params[_p(prefix, 'b')] = numpy.zeros((2 * dim,)).astype('float32')

    # recurrent transformation weights for gates
    U = numpy.concatenate([ortho_weight(dim),
                           ortho_weight(dim)], axis=1)
    params[_p(prefix, 'U')] = U

    # embedding to hidden state proposal weights, biases
    Wx = norm_weight(nin, dim)
    params[_p(prefix, 'Wx')] = Wx
    params[_p(prefix, 'bx')] = numpy.zeros((dim,)).astype('float32')

    # recurrent transformation weights for hidden state proposal
    Ux = ortho_weight(dim)
    params[_p(prefix, 'Ux')] = Ux

    return params


def gru_layer(tparams, state_below, options, prefix='gru', mask=None,
              **kwargs):
    nsteps = state_below.shape[0]
    if state_below.ndim == 3:
        n_samples = state_below.shape[1]
    else:
        n_samples = 1

    dim = tparams[_p(prefix, 'Ux')].shape[1]

    if mask is None:
        mask = tensor.alloc(1., state_below.shape[0], 1)

    # utility function to slice a tensor
    def _slice(_x, n, dim):
        if _x.ndim == 3:
            return _x[:, :, n*dim:(n+1)*dim]
        return _x[:, n*dim:(n+1)*dim]

    # state_below is the input word embeddings
    # input to the gates, concatenated
    state_below_ = tensor.dot(state_below, tparams[_p(prefix, 'W')]) + \
        tparams[_p(prefix, 'b')]
    # input to compute the hidden state proposal
    state_belowx = tensor.dot(state_below, tparams[_p(prefix, 'Wx')]) + \
        tparams[_p(prefix, 'bx')]

    # step function to be used by scan
    # arguments    | sequences |outputs-info| non-seqs
    def _step_slice(m_, x_, xx_, h_, U, Ux):
        preact = tensor.dot(h_, U)
        preact += x_

        # reset and update gates
        r = tensor.nnet.sigmoid(_slice(preact, 0, dim))
        u = tensor.nnet.sigmoid(_slice(preact, 1, dim))

        # compute the hidden state proposal
        preactx = tensor.dot(h_, Ux)
        preactx = preactx * r
        preactx = preactx + xx_

        # hidden state proposal
        h = tensor.tanh(preactx)

        # leaky integrate and obtain next hidden state
        h = u * h_ + (1. - u) * h
        h = m_[:, None] * h + (1. - m_)[:, None] * h_

        return h

    # prepare scan arguments
    seqs = [mask, state_below_, state_belowx]
    init_states = [tensor.alloc(0., n_samples, dim)]
    _step = _step_slice
    shared_vars = [tparams[_p(prefix, 'U')],
                   tparams[_p(prefix, 'Ux')]]

    rval, updates = theano.scan(_step,
                                sequences=seqs,
                                outputs_info=init_states,
                                non_sequences=shared_vars,
                                name=_p(prefix, '_layers'),
                                n_steps=nsteps,
                                profile=profile,
                                strict=True)
    rval = [rval]
    return rval


# Conditional GRU layer without Attention
def param_init_gru_cond_simple(options, params, prefix='gru_cond', nin=None,
                               dim=None, dimctx=None):
    if nin is None:
        nin = options['dim']
    if dim is None:
        dim = options['dim']
    if dimctx is None:
        dimctx = options['dim']

    params = param_init_gru(options, params, prefix, nin=nin, dim=dim)

    # context to GRU gates
    Wc = norm_weight(dimctx, dim*2)
    params[_p(prefix, 'Wc')] = Wc

    # context to hidden proposal
    Wcx = norm_weight(dimctx, dim)
    params[_p(prefix, 'Wcx')] = Wcx

    return params


def gru_cond_simple_layer(tparams, state_below, options, prefix='gru',
                          mask=None, context=None, one_step=False,
                          init_state=None,
                          **kwargs):

    assert context, 'Context must be provided'

    if one_step:
        assert init_state, 'previous state must be provided'

    nsteps = state_below.shape[0]
    if state_below.ndim == 3:
        n_samples = state_below.shape[1]
    else:
        n_samples = 1

    # mask
    if mask is None:
        mask = tensor.alloc(1., state_below.shape[0], 1)

    dim = tparams[_p(prefix, 'Ux')].shape[1]

    # initial/previous state
    if init_state is None:
        init_state = tensor.alloc(0., n_samples, dim)

    assert context.ndim == 2, 'Context must be 2-d: #sample x dim'
    # projected context to GRU gates
    pctx_ = tensor.dot(context, tparams[_p(prefix, 'Wc')])
    # projected context to hidden state proposal
    pctxx_ = tensor.dot(context, tparams[_p(prefix, 'Wcx')])

    def _slice(_x, n, dim):
        if _x.ndim == 3:
            return _x[:, :, n*dim:(n+1)*dim]
        return _x[:, n*dim:(n+1)*dim]

    # projected x to gates
    state_belowx = tensor.dot(state_below, tparams[_p(prefix, 'Wx')]) + \
        tparams[_p(prefix, 'bx')]
    # projected x to hidden state proposal
    state_below_ = tensor.dot(state_below, tparams[_p(prefix, 'W')]) + \
        tparams[_p(prefix, 'b')]

    # step function to be used by scan
    # arguments    | sequences |outputs-info|       non-seqs
    def _step_slice(m_, x_, xx_,    h_,       pctx_, pctxx_, U, Ux):
        preact = tensor.dot(h_, U)
        preact += x_
        preact += pctx_
        preact = tensor.nnet.sigmoid(preact)

        r = _slice(preact, 0, dim)
        u = _slice(preact, 1, dim)

        preactx = tensor.dot(h_, Ux)
        preactx *= r
        preactx += xx_
        preactx += pctxx_

        h = tensor.tanh(preactx)

        h = u * h_ + (1. - u) * h
        h = m_[:, None] * h + (1. - m_)[:, None] * h_

        return h

    seqs = [mask, state_below_, state_belowx]
    _step = _step_slice

    shared_vars = [tparams[_p(prefix, 'U')],
                   tparams[_p(prefix, 'Ux')]]

    if one_step:
        rval = _step(*(seqs+[init_state, pctx_, pctxx_]+shared_vars))
    else:
        rval, updates = theano.scan(_step,
                                    sequences=seqs,
                                    outputs_info=[init_state],
                                    non_sequences=[pctx_,
                                                   pctxx_]+shared_vars,
                                    name=_p(prefix, '_layers'),
                                    n_steps=nsteps,
                                    profile=profile,
                                    strict=True)
    return rval


# Conditional GRU with Attention
def param_init_gru_cond_attention(options, params, prefix='gru_attn', nin=None,
                               dim=None, dimctx=None):
    if nin is None:
        nin = options['dim']
    if dim is None:
        dim = options['dim']
    if dimctx is None:
        dimctx = options['dim']

    params = param_init_gru(options, params, prefix, nin=nin, dim=dim)

    # context to GRU gates
    #Wc = norm_weight(dimctx, dim*2)
    #params[_p(prefix, 'Wc')] = Wc

    # context to hidden proposal
    Wcx = norm_weight(dimctx, dim)
    params[_p(prefix, 'Wcx')] = Wcx

    return params

def gru_cond_attention_layer(tparams, state_below, options, prefix='gru_attn',
                          mask=None, context=None, one_step=False,
                          init_state=None,
                          **kwargs):

    assert context, 'Context must be provided'

    if one_step:
        assert init_state, 'previous state must be provided'

    nsteps = state_below.shape[0]
    if state_below.ndim == 3:
        n_samples = state_below.shape[1]
    else:
        n_samples = 1

    # mask
    if mask is None:
        mask = tensor.alloc(1., state_below.shape[0], 1)

    # score matrix
    #if score_mat is None:
    #    score_mat = tensor.alloc(1., n_samples, nsteps)

    dim = tparams[_p(prefix, 'Ux')].shape[1]

    # initial/previous state
    if init_state is None:
        init_state = tensor.alloc(0., n_samples, dim)

    assert context.ndim == 3, 'Context must be 3-d: #sample x dim'
    # projected context to GRU gates
    #pctx_ = tensor.dot(context, tparams[_p(prefix, 'Wc')])
    # projected context to hidden state proposal
    #This calculates all the attention weights multiplied with enocoder states
    pctxx_ = tensor.dot(context, tparams[_p(prefix, 'Wcx')])
    def _slice(_x, n, dim):
        if _x.ndim == 3:
            return _x[:, :, n*dim:(n+1)*dim]
        return _x[:, n*dim:(n+1)*dim]

    # projected x to gates
    state_belowx = tensor.dot(state_below, tparams[_p(prefix, 'Wx')]) + \
        tparams[_p(prefix, 'bx')]
    # projected x to hidden state proposal
    state_below_ = tensor.dot(state_below, tparams[_p(prefix, 'W')]) + \
        tparams[_p(prefix, 'b')]

    # step function to be used by scan
    #score = theano.shared(numpy.zeros((20,128),dtype=numpy.float32))
    
    # arguments    | sequences |outputs-info|       non-seqs
    def _step_slice(m_, x_, xx_,    h_,score,atn_vec,      pctxx_,cc_, U, Ux):
        preact = tensor.dot(h_, U)
        preact += x_
        #preact += pctx_
        preact = tensor.nnet.sigmoid(preact)

        r = _slice(preact, 0, dim)
        u = _slice(preact, 1, dim)

        #Attention part
        #score = score_mat
        #out1 = theano.shared(np.zeros((6,4)).reshape(2,3,4))
        for i in range(20):
            x = pctxx_[i] * h_ #Element wise product
            x = tensor.sum(x,axis=1)
            score = tensor.set_subtensor(score[i], x)

        #Do column wise softmax
        score = tensor.exp(score)# - score.max(axis=0, keepdims=True))
        score = score / score.sum(0, keepdims=True)
        score = score.reshape([nsteps,n_samples,1])
        score.broadcastable
        #atn_vec = cc_ * score
        #atn_vec = atn_vec.sum(0)

        #h_ += atn_vec
        preactx = tensor.dot(h_, Ux)
        preactx *= r
        preactx += xx_
        #preactx += atn_vec

        h = tensor.tanh(preactx)

        h = u * h_ + (1. - u) * h
        h = m_[:, None] * h + (1. - m_)[:, None] * h_

        return h,score,atn_vec

    seqs = [mask, state_below_, state_belowx]
    _step = _step_slice
    
    shared_vars = [tparams[_p(prefix, 'U')],
                   tparams[_p(prefix, 'Ux')]]

    #tensor.alloc(1., n_samples, nsteps)
    if one_step:
        rval = _step(*(seqs+[init_state, tensor.alloc(0., n_samples, context.shape[0]), tensor.alloc(0., n_samples, context.shape[2]) , pctxx_, context]+shared_vars))
    else:
        rval, updates = theano.scan(_step,
                                    sequences=seqs,
                                    outputs_info=[init_state,
                                            tensor.alloc(0., n_samples, context.shape[0]),
                                            tensor.alloc(0., n_samples, context.shape[2])],
                                    non_sequences=[pctxx_,context]+shared_vars,
                                    name=_p(prefix, '_layers'),
                                    n_steps=nsteps,
                                    profile=profile,
                                    strict=True)
    return rval

# initialize all parameters
def init_params(options):
    params = OrderedDict()
    # embedding
    params['Wemb_encoder'] = norm_weight(options['n_words_src'], options['dim_word'])
    params['Wemb_dec'] = norm_weight(options['n_words'], options['dim_word'])
    # encoder
    params = get_layer(options['encoder'])[0](options, params,
                                              prefix='encoder',
                                              nin=options['dim_word'],
                                              dim=options['dim'])
    ctxdim = options['dim']
    # init_state, init_cell
    params = get_layer('ff')[0](options, params, prefix='ff_state_style0',
                                nin=ctxdim, nout=options['dim'])
    params = get_layer('ff')[0](options, params, prefix='ff_state_style1',
                                nin=ctxdim, nout=options['dim'])

    ctxdim = ctxdim
    params["style_matrix0"] = norm_weight(options["dim"], options["dim"])
    params["style_matrix1"] = norm_weight(options["dim"], options["senti_num"])

    # decoder0
    params = get_layer(options['decoder'])[0](options, params,
                                              prefix='decoder_style0',
                                              nin=options['dim_word'],
                                              dim=options['dim'],
                                              dimctx=ctxdim)
    # readout
    params = get_layer('ff')[0](options, params, prefix='ff_logit_lstm_style0',
                                nin=options['dim'], nout=options['dim_word'],
                                ortho=False)
    params = get_layer('ff')[0](options, params, prefix='ff_logit_prev_style0',
                                nin=options['dim_word'],
                                nout=options['dim_word'], ortho=False)
    params = get_layer('ff')[0](options, params, prefix='ff_logit_ctx_style0',
                                nin=ctxdim, nout=options['dim_word'],
                                ortho=False)
    params = get_layer('ff')[0](options, params, prefix='ff_logit_style0',
                                nin=options['dim_word'],
                                nout=options['n_words'])


    # decoder1
    params = get_layer(options['decoder'])[0](options, params,
                                              prefix='decoder_style1',
                                              nin=options['dim_word'],
                                              dim=options['dim'],
                                              dimctx=ctxdim)
    # readout
    params = get_layer('ff')[0](options, params, prefix='ff_logit_lstm_style1',
                                nin=options['dim'], nout=options['dim_word'],
                                ortho=False)
    params = get_layer('ff')[0](options, params, prefix='ff_logit_prev_style1',
                                nin=options['dim_word'],
                                nout=options['dim_word'], ortho=False)
    params = get_layer('ff')[0](options, params, prefix='ff_logit_ctx_style1',
                                nin=ctxdim, nout=options['dim_word'],
                                ortho=False)
    params = get_layer('ff')[0](options, params, prefix='ff_logit_style1',
                                nin=options['dim_word'],
                                nout=options['n_words'])

    return params


# build a training model
def build_model(tparams, options):
    opt_ret = dict()

    trng = RandomStreams(1234)
    use_noise = theano.shared(numpy.float32(0.))
    #if options['use_dropout']:
    #    use_noise = theano.shared(numpy.float32(1.))
    

    # description string: #words x #samples
    x = tensor.matrix('x', dtype='int64')
    x_mask = tensor.matrix('x_mask', dtype='float32')
    y = tensor.matrix('y', dtype='int64')
    y_mask = tensor.matrix('y_mask', dtype='float32')

    n_timesteps = x.shape[0]
    n_timesteps_trg = y.shape[0]
    n_samples = x.shape[1]

    # word embedding (source)
    xf=x.flatten()
    #xf=theano.printing.Print('xf')(xf)
    emb = tparams['Wemb_encoder'][xf]
    emb = emb.reshape([n_timesteps, n_samples, options['dim_word']])

    # pass through encoder gru, recurrence here
    proj = get_layer(options['encoder'])[1](tparams, emb, options,
                                            prefix='encoder',
                                            mask=x_mask)

    # last hidden state of encoder rnn will be used to initialize decoder rnn
    ctx = proj[0][-1]
    dec_ctx = ctx 
    if options['decoder'] == 'gru_cond_attention':
        dec_ctx = proj[0] #Total context for attention decoder
    ctx_mean = ctx

    #adv part of ctx
    #ctx: sample * dim
    style_matrix0 = tparams["style_matrix0"]
    style_matrix0 = tensor.dot(ctx, style_matrix0)
    style_matrix1 = tparams["style_matrix1"]
    style_matrix = tensor.dot(style_matrix0, style_matrix1)
    #style_matrix = theano.printing.Print('style_matrix_nosoftmax')(style_matrix)
    style_matrix = tensor.nnet.softmax(style_matrix)
    style_matrix_log = tensor.log(style_matrix)
    #style_matrix = theano.printing.Print('style_matrix')(style_matrix)
    #style_matrix_log = theano.printing.Print('style_matrix_log')(style_matrix_log)
    cost_h = style_matrix * style_matrix_log


    si = theano.tensor.ivector('si')
    tensor_eye = tensor.eye(options['senti_num'], dtype="float32")
    label_emb = tensor_eye[si.flatten()]
    #label_emb = theano.printing.Print('label_emb')(label_emb)
    cost_d = label_emb * style_matrix_log * -1



    # word embedding (target), we will shift the target sequence one time step
    # to the right. This is done because of the bi-gram connections in the
    # readout and decoder rnn. The first target will be all zeros and we will
    # not condition on the last output.
    emb = tparams['Wemb_dec'][y.flatten()]
    emb = emb.reshape([n_timesteps_trg, n_samples, options['dim_word']])
    emb_shifted = tensor.zeros_like(emb)
    emb_shifted = tensor.set_subtensor(emb_shifted[1:], emb[:-1])
    emb = emb_shifted

    # initial decoder state
    init_state = get_layer('ff')[1](tparams, ctx_mean, options,
                                    prefix='ff_state_style0', activ='tanh')


    # decoder - pass through the decoder gru, recurrence here
    #score_mat = tensor.alloc(1., n_samples, 20)
    proj = get_layer(options['decoder'])[1](tparams, emb, options,
                                            prefix='decoder_style0',
                                            mask=y_mask,context=dec_ctx,
                                            one_step=False,
                                            init_state=init_state)
    # hidden states of the decoder gru
    proj_h = proj[0] #This would be the hidden state

    # we will condition on the last state of the encoder only
    ctxs = ctx[None, :, :]

    # compute word probabilities
    logit_lstm = get_layer('ff')[1](tparams, proj_h, options,
                                    prefix='ff_logit_lstm_style0', activ='linear')
    logit_prev = get_layer('ff')[1](tparams, emb, options,
                                    prefix='ff_logit_prev_style0', activ='linear')
    logit_ctx = get_layer('ff')[1](tparams, ctxs, options,
                                   prefix='ff_logit_ctx_style0', activ='linear')
    logit = tensor.tanh(logit_lstm+logit_prev+logit_ctx)
    logit = get_layer('ff')[1](tparams, logit, options, prefix='ff_logit_style0',
                               activ='linear')
    logit_shp = logit.shape
    probs = tensor.nnet.softmax(
        logit.reshape([logit_shp[0]*logit_shp[1], logit_shp[2]]))

    # cost0
    y_flat = y.flatten()
    y_flat_idx = tensor.arange(y_flat.shape[0]) * options['n_words'] + y_flat
    cost0 = -tensor.log(probs.flatten()[y_flat_idx])
    cost0 = cost0.reshape([y.shape[0], y.shape[1]])
    cost0 = (cost0 * y_mask).sum(0)



    init_state1 = get_layer('ff')[1](tparams, ctx_mean, options,
                                    prefix='ff_state_style1', activ='tanh')


    # decoder - pass through the decoder gru, recurrence here
    proj1 = get_layer(options['decoder'])[1](tparams, emb, options,
                                            prefix='decoder_style1',
                                            mask=y_mask, context=dec_ctx,
                                            one_step=False,
                                            init_state=init_state1)
    # hidden states of the decoder gru
    proj_h1 = proj1[0]

    # we will condition on the last state of the encoder only
    ctxs = ctx[None, :, :]

    # compute word probabilities
    logit_lstm1 = get_layer('ff')[1](tparams, proj_h1, options,
                                    prefix='ff_logit_lstm_style1', activ='linear')
    logit_prev1 = get_layer('ff')[1](tparams, emb, options,
                                    prefix='ff_logit_prev_style1', activ='linear')
    logit_ctx1 = get_layer('ff')[1](tparams, ctxs, options,
                                   prefix='ff_logit_ctx_style1', activ='linear')
    logit1 = tensor.tanh(logit_lstm1+logit_prev1+logit_ctx1)
    logit1 = get_layer('ff')[1](tparams, logit1, options, prefix='ff_logit_style1',
                               activ='linear')
    logit_shp1 = logit1.shape
    probs1 = tensor.nnet.softmax(
        logit1.reshape([logit_shp1[0]*logit_shp1[1], logit_shp1[2]]))

    # cost0
    y_flat = y.flatten()
    y_flat_idx = tensor.arange(y_flat.shape[0]) * options['n_words'] + y_flat
    cost1 = -tensor.log(probs1.flatten()[y_flat_idx])
    cost1 = cost1.reshape([y.shape[0], y.shape[1]])
    cost1 = (cost1 * y_mask).sum(0)



    return trng, use_noise, x, x_mask, y, y_mask, si, opt_ret, cost0, cost1, cost_d, cost_h


# build a sampler
def build_sampler(tparams, options, trng, use_noise, style_type):
    x = tensor.matrix('x', dtype='int64')
    n_timesteps = x.shape[0]
    n_samples = x.shape[1]

    # word embedding (source)
    emb = tparams['Wemb_encoder'][x.flatten()]
    emb = emb.reshape([n_timesteps, n_samples, options['dim_word']])

    # encoder
    proj = get_layer(options['encoder'])[1](tparams, emb, options,
                                            prefix='encoder')
    ctx = proj[0][-1]
    ctx_mean = ctx

    init_state = get_layer('ff')[1](tparams, ctx_mean, options,
                                    prefix='ff_state_style'+style_type, activ='tanh')



    print 'Building f_init...',
    outs = [init_state, ctx]
    f_init = theano.function([x], outs, name='f_init'+style_type, profile=profile)
    print 'Done'

    
    # y: 1 x 1
    y = tensor.vector('y_sampler', dtype='int64')
    init_state = tensor.matrix('init_state', dtype='float32')

    # if it's the first word, emb should be all zero
    emb = tensor.switch(y[:, None] < 0,
                        tensor.alloc(0., 1, tparams['Wemb_dec'].shape[1]),
                        tparams['Wemb_dec'][y])
    dec_ctx = ctx 
    if options['decoder'] == 'gru_cond_attention':
        dec_ctx = proj[0] #Total context for attention decoder

    # apply one step of gru layer
    proj = get_layer(options['decoder'])[1](tparams, emb, options,
                                            prefix='decoder_style'+style_type,
                                            mask=None, context=dec_ctx,
                                            one_step=True,
                                            init_state=init_state)
    next_state = proj[0]
    ctxs = ctx

    # compute the output probability dist and sample
    logit_lstm = get_layer('ff')[1](tparams, next_state, options,
                                    prefix='ff_logit_lstm_style'+style_type, activ='linear')
    logit_prev = get_layer('ff')[1](tparams, emb, options,
                                    prefix='ff_logit_prev_style'+style_type, activ='linear')
    logit_ctx = get_layer('ff')[1](tparams, ctxs, options,
                                   prefix='ff_logit_ctx_style'+style_type, activ='linear')
    logit = tensor.tanh(logit_lstm+logit_prev+logit_ctx)
    logit = get_layer('ff')[1](tparams, logit, options,
                               prefix='ff_logit_style'+style_type, activ='linear')
    next_probs = tensor.nnet.softmax(logit)
    next_sample = trng.multinomial(pvals=next_probs).argmax(1)

    # next word probability
    print 'Building f_next..',
    inps = [y, ctx, init_state]
    outs = [next_probs, next_sample, next_state]
    f_next = theano.function(inps, outs, name='f_next'+style_type, profile=profile)
    print 'Done'

    return f_init, f_next


# generate sample, either with stochastic sampling or beam search
def gen_sample(tparams, f_init, f_next, x, senti_input, options, trng=None, k=1, maxlen=30,
               stochastic=True, argmax=False):

    # k is the beam size we have
    if k > 1:
        assert not stochastic, \
            'Beam search does not support stochastic sampling'

    sample = []
    sample_score = []
    if stochastic:
        sample_score = 0

    live_k = 1
    dead_k = 0

    hyp_samples = [[]] * live_k
    hyp_scores = numpy.zeros(live_k).astype('float32')
    hyp_states = []

    # get initial state of decoder rnn and encoder context
    ret = f_init(x)
    next_state, ctx0 = ret[0], ret[1]
    next_w = [-1]  # indicator for the first target word (bos target)

    for ii in xrange(maxlen):
        ctx = numpy.tile(ctx0, [live_k, 1])
        inps = [next_w, ctx, next_state]
        ret = f_next(*inps)
        next_p, next_w, next_state = ret[0], ret[1], ret[2]

        if stochastic:
            if argmax:
                nw = next_p[0].argmax()
            else:
                nw = next_w[0]
            sample.append(nw)
            sample_score -= numpy.log(next_p[0, nw])
            if nw == 0:
                break
        else:
            cand_scores = hyp_scores[:, None] - numpy.log(next_p)
            cand_flat = cand_scores.flatten()
            ranks_flat = cand_flat.argsort()[:(k-dead_k)]

            voc_size = next_p.shape[1]
            trans_indices = ranks_flat / voc_size
            word_indices = ranks_flat % voc_size
            costs = cand_flat[ranks_flat]

            new_hyp_samples = []
            new_hyp_scores = numpy.zeros(k-dead_k).astype('float32')
            new_hyp_states = []

            for idx, [ti, wi] in enumerate(zip(trans_indices, word_indices)):
                new_hyp_samples.append(hyp_samples[ti]+[wi])
                new_hyp_scores[idx] = copy.copy(costs[idx])
                new_hyp_states.append(copy.copy(next_state[ti]))

            # check the finished samples
            new_live_k = 0
            hyp_samples = []
            hyp_scores = []
            hyp_states = []

            for idx in xrange(len(new_hyp_samples)):
                if new_hyp_samples[idx][-1] == 0:
                    sample.append(new_hyp_samples[idx])
                    sample_score.append(new_hyp_scores[idx])
                    dead_k += 1
                else:
                    new_live_k += 1
                    hyp_samples.append(new_hyp_samples[idx])
                    hyp_scores.append(new_hyp_scores[idx])
                    hyp_states.append(new_hyp_states[idx])
            hyp_scores = numpy.array(hyp_scores)
            live_k = new_live_k

            if new_live_k < 1:
                break
            if dead_k >= k:
                break

            next_w = numpy.array([w[-1] for w in hyp_samples])
            next_state = numpy.array(hyp_states)

    if not stochastic:
        # dump every remaining one
        if live_k > 0:
            for idx in xrange(live_k):
                sample.append(hyp_samples[idx])
                sample_score.append(hyp_scores[idx])

    return sample, sample_score


# calculate the log probablities on a given corpus using translation model
def pred_probs(f_log_probs, prepare_data, options, iterator, verbose=False):
    probs = []

    n_done = 0

    for x, y, senti, style_index in iterator:
        n_done += len(x)

        x, x_mask, y, y_mask, senti = prepare_data(x, y, senti,
                                            n_words_src=options['n_words_src'],
                                            n_words=options['n_words'])

        pprobs = f_log_probs(x, x_mask, y, y_mask)
        for pp in pprobs:
            probs.append(pp)

        if numpy.isnan(numpy.mean(probs)):
            ipdb.set_trace()

        if verbose:
            print >>sys.stderr, '%d samples computed' % (n_done)

    return numpy.array(probs)


# optimizers
# name(hyperp, tparams, grads, inputs (list), cost) = f_grad_shared, f_update
def adam(lr, tparams, grads, inp, cost, beta1=0.9, beta2=0.999, e=1e-8):

    gshared = [theano.shared(p.get_value() * 0., name='%s_grad' % k)
               for k, p in tparams.iteritems()]
    gsup = [(gs, g) for gs, g in zip(gshared, grads)]

    f_grad_shared = theano.function(inp, cost, updates=gsup, profile=profile)

    updates = []

    t_prev = theano.shared(numpy.float32(0.))
    t = t_prev + 1.
    lr_t = lr * tensor.sqrt(1. - beta2**t) / (1. - beta1**t)

    for p, g in zip(tparams.values(), gshared):
        m = theano.shared(p.get_value() * 0., p.name + '_mean')
        v = theano.shared(p.get_value() * 0., p.name + '_variance')
        m_t = beta1 * m + (1. - beta1) * g
        v_t = beta2 * v + (1. - beta2) * g**2
        step = lr_t * m_t / (tensor.sqrt(v_t) + e)
        p_t = p - step
        updates.append((m, m_t))
        updates.append((v, v_t))
        updates.append((p, p_t))
    updates.append((t_prev, t))

    f_update = theano.function([lr], [], updates=updates,
                               on_unused_input='ignore', profile=profile)

    return f_grad_shared, f_update


def adadelta(lr, tparams, grads, inp, cost, cost_d, cost_h, opti_index):
    zipped_grads = [theano.shared(p.get_value() * numpy.float32(0.),
                                  name='%s_grad_%s' % (k, opti_index))
                    for k, p in tparams.iteritems()]
    running_up2 = [theano.shared(p.get_value() * numpy.float32(0.),
                                 name='%s_rup2_%s' % (k, opti_index))
                   for k, p in tparams.iteritems()]
    running_grads2 = [theano.shared(p.get_value() * numpy.float32(0.),
                                    name='%s_rgrad2_%s' % (k, opti_index))
                      for k, p in tparams.iteritems()]

    zgup = [(zg, g) for zg, g in zip(zipped_grads, grads)]
    rg2up = [(rg2, 0.95 * rg2 + 0.05 * (g ** 2))
             for rg2, g in zip(running_grads2, grads)]

    f_grad_shared = theano.function(inp, [cost, cost_d, cost_h], updates=zgup+rg2up,
                                    profile=profile)

    updir = [-tensor.sqrt(ru2 + 1e-6) / tensor.sqrt(rg2 + 1e-6) * zg
             for zg, ru2, rg2 in
             zip(zipped_grads, running_up2, running_grads2)]
    ru2up = [(ru2, 0.95 * ru2 + 0.05 * (ud ** 2))
             for ru2, ud in zip(running_up2, updir)]
    param_up = [(p, p + ud) for p, ud in zip(itemlist(tparams), updir)]

    f_update = theano.function([lr], [], updates=ru2up+param_up,
                               on_unused_input='ignore', profile=profile)

    return f_grad_shared, f_update


def rmsprop(lr, tparams, grads, inp, cost):
    zipped_grads = [theano.shared(p.get_value() * numpy.float32(0.),
                                  name='%s_grad' % k)
                    for k, p in tparams.iteritems()]
    running_grads = [theano.shared(p.get_value() * numpy.float32(0.),
                                   name='%s_rgrad' % k)
                     for k, p in tparams.iteritems()]
    running_grads2 = [theano.shared(p.get_value() * numpy.float32(0.),
                                    name='%s_rgrad2' % k)
                      for k, p in tparams.iteritems()]

    zgup = [(zg, g) for zg, g in zip(zipped_grads, grads)]
    rgup = [(rg, 0.95 * rg + 0.05 * g) for rg, g in zip(running_grads, grads)]
    rg2up = [(rg2, 0.95 * rg2 + 0.05 * (g ** 2))
             for rg2, g in zip(running_grads2, grads)]

    f_grad_shared = theano.function(inp, cost, updates=zgup+rgup+rg2up,
                                    profile=profile)

    updir = [theano.shared(p.get_value() * numpy.float32(0.),
                           name='%s_updir' % k)
             for k, p in tparams.iteritems()]
    updir_new = [(ud, 0.9 * ud - 1e-4 * zg / tensor.sqrt(rg2 - rg ** 2 + 1e-4))
                 for ud, zg, rg, rg2 in zip(updir, zipped_grads, running_grads,
                                            running_grads2)]
    param_up = [(p, p + udn[1])
                for p, udn in zip(itemlist(tparams), updir_new)]
    f_update = theano.function([lr], [], updates=updir_new+param_up,
                               on_unused_input='ignore', profile=profile)

    return f_grad_shared, f_update


def sgd(lr, tparams, grads, x, mask, y, cost):
    gshared = [theano.shared(p.get_value() * 0., name='%s_grad' % k)
               for k, p in tparams.iteritems()]
    gsup = [(gs, g) for gs, g in zip(gshared, grads)]

    f_grad_shared = theano.function([x, mask, y], cost, updates=gsup,
                                    profile=profile)

    pup = [(p, p - lr * g) for p, g in zip(itemlist(tparams), gshared)]
    f_update = theano.function([lr], [], updates=pup, profile=profile)

    return f_grad_shared, f_update


def train(dim_word=100,  # word vector dimensionality
          dim=1000,  # the number of GRU units
          encoder='gru',
          decoder='gru_cond_attention',
          patience=10,  # early stopping patience
          max_epochs=8,
          finish_after=10000000,  # finish after this many updates
          dispFreq=100,
          decay_c=0.,  # L2 regularization penalty
          alpha_c=0.,  # not used
          lrate=0.01,  # learning rate
          n_words_src=100000,  # source vocabulary size
          n_words=100000,  # target vocabulary size
          maxlen=100,  # maximum length of the description
          optimizer='rmsprop',
          batch_size=16,
          valid_batch_size=16,
          saveto='model.npz',
          validFreq=1000,
          saveFreq=1000,  # save the parameters after every saveFreq updates
          sampleFreq=100,  # generate some samples after every sampleFreq
          datasets=[
              '/data/lisatmp3/chokyun/europarl/europarl-v7.fr-en.en.tok',
              '/data/lisatmp3/chokyun/europarl/europarl-v7.fr-en.fr.tok'],
          valid_datasets=['../data/dev/newstest2011.en.tok',
                          '../data/dev/newstest2011.fr.tok'],
          dictionaries=[
              '/data/lisatmp3/chokyun/europarl/europarl-v7.fr-en.en.tok.pkl',
              '/data/lisatmp3/chokyun/europarl/europarl-v7.fr-en.fr.tok.pkl'],
          use_dropout=False,
          reload_=False,
          overwrite=False,
          senti_num=2,
          senti_dim=128,
          weight_d=1.,
          weight_h=1.,
          style_class=True,
          style_adv=True,
          adv_thre=0.2):

    # Model options
    model_options = locals().copy()

    # load dictionaries and invert them
    worddicts = [None] * len(dictionaries)
    worddicts_r = [None] * len(dictionaries)
    for ii, dd in enumerate(dictionaries):
        with open(dd, 'rb') as f:
            worddicts[ii] = pkl.load(f)
        worddicts_r[ii] = dict()
        for kk, vv in worddicts[ii].iteritems():
            worddicts_r[ii][vv] = kk

    # reload options
    if reload_ and os.path.exists(saveto):
        print 'Reloading model options'
        with open('%s.pkl' % saveto, 'rb') as f:
            model_options = pkl.load(f)

    print 'Loading data'
    train = TextIterator(datasets[0], datasets[1], datasets[2],
                         dictionaries[0], dictionaries[1],
                         n_words_source=n_words_src, n_words_target=n_words,
                         batch_size=batch_size,
                         maxlen=maxlen)
    valid = TextIterator(valid_datasets[0], valid_datasets[1], valid_datasets[2],
                         dictionaries[0], dictionaries[1],
                         n_words_source=n_words_src, n_words_target=n_words,
                         batch_size=valid_batch_size,
                         maxlen=maxlen, val=True)

    print 'Building model'
    params = init_params(model_options)
    # reload parameters
    if reload_ and os.path.exists(saveto):
        print 'Reloading model parameters'
        params = load_params(saveto, params)

    tparams = init_tparams(params)

    trng, use_noise, \
        x, x_mask, y, y_mask, si, \
        opt_ret, \
        cost0, cost1, cost_d, cost_h = \
        build_model(tparams, model_options)
    inps = [x, x_mask, y, y_mask]
    inps1 = [x, x_mask, y, y_mask, si]

    print 'Building sampler'
    f_init0, f_next0 = build_sampler(tparams, model_options, trng, use_noise, "0")
    f_init1, f_next1 = build_sampler(tparams, model_options, trng, use_noise, "1")

    # before any regularizer
    print 'Building f_log_probs...',
    f_log_probs0 = theano.function(inps, cost0, profile=profile)
    f_log_probs1 = theano.function(inps, cost1, profile=profile)
    print 'Done'

    cost0 = cost0.mean()
    cost1 = cost1.mean()
    cost_d = cost_d.mean()
    cost_h = cost_h.mean()

    # apply L2 regularization on weights
    if decay_c > 0.:
        decay_c = theano.shared(numpy.float32(decay_c), name='decay_c')
        weight_decay = 0.
        for kk, vv in tparams.iteritems():
            weight_decay += (vv ** 2).sum()
        weight_decay *= decay_c
        cost0 += weight_decay
        cost1 += weight_decay

    # un used, attention weight regularization
    if alpha_c > 0. and not model_options['decoder'].endswith('simple'):
        alpha_c = theano.shared(numpy.float32(alpha_c), name='alpha_c')
        alpha_reg = alpha_c * (
            (tensor.cast(y_mask.sum(0)//x_mask.sum(0), 'float32')[:, None] -
             opt_ret['dec_alphas'].sum(0))**2).sum(1).mean()
        cost0 += alpha_reg
        cost1 += alpha_reg

    # after all regularizers - compile the computational graph for cost
    print 'Building f_cost...',
    f_cost0 = theano.function(inps, cost0, profile=profile)
    f_cost1 = theano.function(inps, cost1, profile=profile)
    print 'Done'

    print 'Computing gradient...',
    grads_o0 = tensor.grad(cost0, wrt=itemlist(tparams), disconnected_inputs='ignore')
    grads_o1 = tensor.grad(cost1, wrt=itemlist(tparams), disconnected_inputs='ignore')
    grads_d = tensor.grad(cost_d, wrt=itemlist(tparams), disconnected_inputs='ignore')
    grads_h = tensor.grad(cost_h, wrt=itemlist(tparams), disconnected_inputs='ignore')
    #print len(grads_o)
    #print len(grads_d)
    #print len(grads_h)
    
    grads0 = []
    i = 0
    for kk,vv in tparams.iteritems():
        if kk=="style_matrix" and style_class:
            grads0.append(grads_o0[i]+grads_d[i]*weight_d)
        elif "encoder" in kk and style_adv:
            grads0.append(grads_o0[i]+grads_h[i]*weight_h)
        else:
            grads0.append(grads_o0[i])
        i += 1

    grads1 = []
    i = 0
    for kk,vv in tparams.iteritems():
        if kk=="style_matrix" and style_class:
            grads1.append(grads_o1[i]+grads_d[i]*weight_d)
        elif "encoder" in kk and style_adv:
            grads1.append(grads_o1[i]+grads_h[i]*weight_h)
        else:
            grads1.append(grads_o1[i])
        i += 1



    print 'Done'
    use_adv = False
    # compile the optimizer, the actual computational graph is compiled here
    lr = tensor.scalar(name='lr')
    print 'Building optimizers...',
    f_grad_shared0, f_update0 = eval(optimizer)(lr, tparams, grads0, inps1, cost0, cost_d, cost_h, "0")
    f_grad_shared1, f_update1 = eval(optimizer)(lr, tparams, grads1, inps1, cost1, cost_d, cost_h, "1")
    f_grad_shared = [ f_grad_shared0, f_grad_shared1]
    f_update = [ f_update0, f_update1]
    print 'Done'


    print 'Optimization'

    best_p = None
    bad_counter = 0
    uidx = 0
    estop = False
    history_errs = []
    # reload history
    if reload_ and os.path.exists(saveto):
        rmodel = numpy.load(saveto)
        history_errs = list(rmodel['history_errs'])
        if 'uidx' in rmodel:
            uidx = rmodel['uidx']

    if validFreq == -1:
        validFreq = len(train[0])/batch_size
    if saveFreq == -1:
        saveFreq = len(train[0])/batch_size
    if sampleFreq == -1:
        sampleFreq = len(train[0])/batch_size

    for eidx in xrange(max_epochs):
        n_samples = 0

        for x, y, senti, senti_index in train:
            n_samples += len(x)
            uidx += 1
            use_noise.set_value(1.)

            x, x_mask, y, y_mask, senti = prepare_data(x, y, senti, maxlen=maxlen,
                                                n_words_src=n_words_src,
                                                n_words=n_words)

            #print senti_index, senti[:10]
            if x is None:
                print 'Minibatch with zero sample under length ', maxlen
                uidx -= 1
                continue

            ud_start = time.time()

            
            # compute cost, grads and copy grads to shared variables
            cost, cost_d, cost_h = f_grad_shared[senti_index](x, x_mask, y, y_mask, senti)
            # do the update on parameters
            f_update[senti_index](lrate)
           

            ud = time.time() - ud_start

            # check for bad numbers, usually we remove non-finite elements
            # and continue training - but not done here
            if numpy.isnan(cost) or numpy.isinf(cost):
                print 'NaN detected'
                return 1., 1., 1.

            # verbose
            if numpy.mod(uidx, dispFreq) == 0:
                print 'Epoch ', eidx, 'Update ', uidx, 'style ', senti_index, 'Cost ', cost, cost_d, cost_h, 'UD ', ud

            # save the best model so far, in addition, save the latest model
            # into a separate file with the iteration number for external eval
            if numpy.mod(uidx, saveFreq) == 0:
                print 'Saving the best model...',
                if best_p is not None:
                    params = best_p
                else:
                    params = unzip(tparams)
                numpy.savez(saveto, history_errs=history_errs, uidx=uidx, **params)
                pkl.dump(model_options, open('%s.pkl' % saveto, 'wb'))
                print 'Done'

                # save with uidx
                if not overwrite:
                    print 'Saving the model at iteration {}...'.format(uidx),
                    saveto_uidx = '{}.iter{}.npz'.format(
                        os.path.splitext(saveto)[0], uidx)
                    numpy.savez(saveto_uidx, history_errs=history_errs,
                                uidx=uidx, **unzip(tparams))
                    print 'Done'


            # generate some samples with the model and display them
            if numpy.mod(uidx, sampleFreq) == 0:
                # FIXME: random selection?
                for jj in xrange(numpy.minimum(5, x.shape[1])):
                    stochastic = True
                    sample, score = gen_sample(tparams, f_init0, f_next0,
                                               x[:, jj][:, None], senti[jj:jj+1],
                                               model_options, trng=trng, k=1,
                                               maxlen=30,
                                               stochastic=stochastic,
                                               argmax=False)

                    sample1, score1 = gen_sample(tparams, f_init1, f_next1,
                                               x[:, jj][:, None], 1-senti[jj:jj+1],
                                               model_options, trng=trng, k=1,
                                               maxlen=30,
                                               stochastic=stochastic,
                                               argmax=False)


                    print 'Source ', jj, ': ',
                    for vv in x[:, jj]:
                        if vv == 0:
                            break
                        if vv in worddicts_r[0]:
                            print worddicts_r[0][vv],
                        else:
                            print 'UNK',
                    print
                    print 'Truth ', jj, ' : ',
                    for vv in y[:, jj]:
                        if vv == 0:
                            break
                        if vv in worddicts_r[1]:
                            print worddicts_r[1][vv],
                        else:
                            print 'UNK',
                    print
                    print 'Sample ', jj, ' senti ', senti[jj:jj+1], ': ',
                    if stochastic:
                        ss = sample
                    else:
                        score = score / numpy.array([len(s) for s in sample])
                        ss = sample[score.argmin()]
                    for vv in ss:
                        if vv == 0:
                            break
                        if vv in worddicts_r[1]:
                            print worddicts_r[1][vv],
                        else:
                            print 'UNK',
                    print


                    print 'Sample ', jj, ' senti ', 1-senti[jj:jj+1], ': ',
                    if stochastic:
                        ss = sample1
                    else:
                        score1 = score1 / numpy.array([len(s) for s in sample1])
                        ss = sample1[score1.argmin()]
                    for vv in ss:
                        if vv == 0:
                            break
                        if vv in worddicts_r[1]:
                            print worddicts_r[1][vv],
                        else:
                            print 'UNK',

                    print

            # validate model on validation set and early stop if necessary
            if numpy.mod(uidx, validFreq) == 0:
                use_noise.set_value(0.)
                valid_errs0 = pred_probs(f_log_probs0, prepare_data,
                                        model_options, valid)
                valid_errs1 = pred_probs(f_log_probs1, prepare_data,
                                        model_options, valid)
                #print valid_errs0
                #print valid_errs1
                if len(valid_errs0)==0:
                    v0 = .0
                else:
                    v0 = valid_errs0.mean()
                if len(valid_errs1)==0:
                    v1 = .0
                else:
                    v1 = valid_errs1.mean()
                    
                valid_err = v0 + v1
                history_errs.append(valid_err)

                if uidx == 0 or valid_err <= numpy.array(history_errs).min():
                    best_p = unzip(tparams)
                    bad_counter = 0
                if len(history_errs) > patience and valid_err >= \
                        numpy.array(history_errs)[:-patience].min():
                    bad_counter += 1
                    if bad_counter > patience:
                        print 'Early Stop!'
                        estop = True
                        break

                if numpy.isnan(valid_err):
                    ipdb.set_trace()

                print 'Valid ', valid_err

            # finish after this many updates
            if uidx >= finish_after:
                print 'Finishing after %d iterations!' % uidx
                estop = True
                break

        print 'Seen %d samples' % n_samples

        if estop:
            break

    if best_p is not None:
        zipp(best_p, tparams)

    use_noise.set_value(0.)
    valid_err0 = pred_probs(f_log_probs0, prepare_data,
                           model_options, valid).mean()
    valid_err1 = pred_probs(f_log_probs1, prepare_data,
                           model_options, valid).mean()
    valid_err = valid_err0 + valid_err1
    print 'Valid ', valid_err

    params = copy.copy(best_p)
    numpy.savez(saveto, zipped_params=best_p,
                history_errs=history_errs,
                uidx=uidx,
                **params)

    return valid_err


if __name__ == '__main__':
    pass
