import torch
import os
import cPickle as pkl
from datasets import load_dataset
from vocab import build_dictionary
import homogeneous_data
from torch.autograd import Variable
import time
from model import jianzhuNet, PairwiseRankingLoss
import numpy
from tools import encode_sentences, encode_images
from evaluation import i2t, t2i, i2t_arch, t2i_arch


def trainer(data='coco',
            margin=0.2,
            dim=1024,
            dim_image=4096,
            dim_word=300,
            encoder='gru',
            max_epochs=15,
            dispFreq=10,
            decay_c=0.0,
            grad_clip=2.0,
            maxlen_w=150,
            optimizer='adam',
            batch_size=128,
            saveto='vse/coco.npz',
            validFreq=100,
            lrate=0.0002,
            reload_=False):

    # Model options
    model_options = {}
    model_options['data'] = data
    model_options['margin'] = margin
    model_options['dim'] = dim
    model_options['dim_image'] = dim_image
    model_options['dim_word'] = dim_word
    model_options['encoder'] = encoder
    model_options['max_epochs'] = max_epochs
    model_options['dispFreq'] = dispFreq
    model_options['decay_c'] = decay_c
    model_options['grad_clip'] = grad_clip
    model_options['maxlen_w'] = maxlen_w
    model_options['optimizer'] = optimizer
    model_options['batch_size'] = batch_size
    model_options['saveto'] = saveto
    model_options['validFreq'] = validFreq
    model_options['lrate'] = lrate
    model_options['reload_'] = reload_

    print model_options

    # reload options
    if reload_ and os.path.exists(saveto):
        print 'reloading...' + saveto
        with open('%s.pkl'%saveto, 'rb') as f:
            model_options = pkl.load(f)

    # Load training and development sets
    print 'loading dataset'
    train, dev = load_dataset(data)[:2]

    # Create and save dictionary
    print 'Create dictionary'
    worddict = build_dictionary(train[0]+dev[0])[0]
    n_words = len(worddict)
    model_options['n_words'] = n_words
    print 'Dictionary size: ' + str(n_words)
    with open('%s.dictionary.pkl'%saveto, 'wb') as f:
        pkl.dump(worddict, f)


    # Inverse dictionary
    word_idict = dict()
    for kk, vv in worddict.iteritems():
        word_idict[vv] = kk
    word_idict[0] = '<eos>'
    word_idict[1] = 'UNK'

    # TODO: init_params and init_tparams

    # Each sentence in the minibatch have same length (for encoder)
    train_iter = homogeneous_data.HomogeneousData([train[0], train[1]], batch_size=batch_size, maxlen=maxlen_w)

    jianzhu_model = jianzhuNet(model_options)
    jianzhu_model = jianzhu_model.cuda()

    loss_fn = PairwiseRankingLoss(margin=margin)
    loss_fn = loss_fn.cuda()

    params = filter(lambda p: p.requires_grad, jianzhu_model.parameters())
    optimizer = torch.optim.Adam(params, lrate)

    uidx = 0
    curr = 0.0
    n_samples = 0

    for eidx in xrange(max_epochs):

        print 'Epoch ', eidx

        for x, im in train_iter:
            n_samples += len(x)
            uidx += 1

            x, im = homogeneous_data.prepare_data(x, im, worddict, maxlen=maxlen_w, n_words=n_words)

            if x == None:
                print 'Minibatch with zero sample under length ', maxlen_w
                uidx -= 1
                continue

            x = Variable(torch.from_numpy(x).cuda())
            im = Variable(torch.from_numpy(im).cuda())
            # Update
            ud_start = time.time()
            x, im = jianzhu_model(x, im)
            cost = loss_fn(im, x)
            optimizer.zero_grad()
            cost.backward()
            torch.nn.utils.clip_grad_norm(params, grad_clip)
            optimizer.step()
            ud = time.time() - ud_start

            if numpy.mod(uidx, dispFreq) == 0:
                print 'Epoch ', eidx, 'Update ', uidx, 'Cost ', cost.data.cpu().numpy()[0], 'UD ', ud

            if numpy.mod(uidx, validFreq) == 0:

                print 'Computing results...'
                curr_model = {}
                curr_model['options'] = model_options
                curr_model['worddict'] = worddict
                curr_model['word_idict'] = word_idict
                curr_model['jianzhu_model'] = jianzhu_model

                ls, lim = encode_sentences(curr_model, dev[0]), encode_images(curr_model, dev[1])

                r1, r5, r10, medr = 0.0, 0.0, 0.0, 0
                r1i, r5i, r10i, medri = 0.0, 0.0, 0.0, 0
                if data == 'arch':
                    (r1, r5, r10, medr) = i2t_arch(lim, ls)
                    print "Image to text: %.1f, %.1f, %.1f, %.1f" % (r1, r5, r10, medr)
                    (r1i, r5i, r10i, medri) = t2i_arch(lim, ls)
                    print "Text to image: %.1f, %.1f, %.1f, %.1f" % (r1i, r5i, r10i, medri)
                else:
                    (r1, r5, r10, medr) = i2t(lim, ls)
                    print "Image to text: %.1f, %.1f, %.1f, %.1f" % (r1, r5, r10, medr)
                    (r1i, r5i, r10i, medri) = t2i(lim, ls)
                    print "Text to image: %.1f, %.1f, %.1f, %.1f" % (r1i, r5i, r10i, medri)

                currscore = r1 + r5 + r10 + r1i + r5i + r10i
                if currscore > curr:
                    curr = currscore

                    # # Save model
                    # print 'Saving...',
                    # params = unzip(tparams)
                    # numpy.savez(saveto, **params)
                    # pkl.dump(model_options, open('%s.pkl'%saveto, 'wb'))
                    # print 'Done'

        print 'Seen %d samples'%n_samples

if __name__ == '__main__':
    pass
