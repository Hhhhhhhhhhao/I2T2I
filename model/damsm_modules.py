import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
from torchvision import models
import torch.utils.model_zoo as model_zoo
from base import BaseModel

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


def conv1x1(in_planes, out_planes, bias=False):
    "1x1 convolution with padding"
    return nn.Conv2d(in_planes, out_planes, kernel_size=1, stride=1,
                     padding=0, bias=bias)


def conv3x3(in_planes, out_planes):
    "3x3 convolution with padding"
    return nn.Conv2d(in_planes, out_planes, kernel_size=3, stride=1,
                     padding=1, bias=False)


class DAMSM_CNN_Encoder(BaseModel):
    def __init__(self,
                 embedding_size=256):
        super(DAMSM_CNN_Encoder, self).__init__()
        self.embedding_size = embedding_size  # define a uniform ranker

        model = models.inception_v3()
        url = 'https://download.pytorch.org/models/inception_v3_google-1a9a5a14.pth'
        model.load_state_dict(model_zoo.load_url(url))
        for param in model.parameters():
            param.requires_grad = False
        print('Load pretrained model from ', url)
        self.define_module(model)
        self.init_trainable_weights()

    def define_module(self, model):
        self.Conv2d_1a_3x3 = model.Conv2d_1a_3x3
        self.Conv2d_2a_3x3 = model.Conv2d_2a_3x3
        self.Conv2d_2b_3x3 = model.Conv2d_2b_3x3
        self.Conv2d_3b_1x1 = model.Conv2d_3b_1x1
        self.Conv2d_4a_3x3 = model.Conv2d_4a_3x3
        self.Mixed_5b = model.Mixed_5b
        self.Mixed_5c = model.Mixed_5c
        self.Mixed_5d = model.Mixed_5d
        self.Mixed_6a = model.Mixed_6a
        self.Mixed_6b = model.Mixed_6b
        self.Mixed_6c = model.Mixed_6c
        self.Mixed_6d = model.Mixed_6d
        self.Mixed_6e = model.Mixed_6e
        self.Mixed_7a = model.Mixed_7a
        self.Mixed_7b = model.Mixed_7b
        self.Mixed_7c = model.Mixed_7c

        self.emb_features = conv1x1(768, self.embedding_size)
        self.emb_cnn_code = nn.Linear(2048, self.embedding_size)

    def init_trainable_weights(self):
        initrange = 0.1
        self.emb_features.weight.data.uniform_(-initrange, initrange)
        self.emb_cnn_code.weight.data.uniform_(-initrange, initrange)

    def forward(self, x):
        features = None
        # --> fixed-size input: batch x 3 x 299 x 299
        x = nn.Upsample(size=(299, 299), mode='bilinear', align_corners=False)(x)
        # 299 x 299 x 3
        x = self.Conv2d_1a_3x3(x)
        # 149 x 149 x 32
        x = self.Conv2d_2a_3x3(x)
        # 147 x 147 x 32
        x = self.Conv2d_2b_3x3(x)
        # 147 x 147 x 64
        x = F.max_pool2d(x, kernel_size=3, stride=2)
        # 73 x 73 x 64
        x = self.Conv2d_3b_1x1(x)
        # 73 x 73 x 80
        x = self.Conv2d_4a_3x3(x)
        # 71 x 71 x 192

        x = F.max_pool2d(x, kernel_size=3, stride=2)
        # 35 x 35 x 192
        x = self.Mixed_5b(x)
        # 35 x 35 x 256
        x = self.Mixed_5c(x)
        # 35 x 35 x 288
        x = self.Mixed_5d(x)
        # 35 x 35 x 288

        x = self.Mixed_6a(x)
        # 17 x 17 x 768
        x = self.Mixed_6b(x)
        # 17 x 17 x 768
        x = self.Mixed_6c(x)
        # 17 x 17 x 768
        x = self.Mixed_6d(x)
        # 17 x 17 x 768
        x = self.Mixed_6e(x)
        # 17 x 17 x 768

        # image region features
        features = x
        # 17 x 17 x 768

        x = self.Mixed_7a(x)
        # 8 x 8 x 1280
        x = self.Mixed_7b(x)
        # 8 x 8 x 2048
        x = self.Mixed_7c(x)
        # 8 x 8 x 2048
        x = F.avg_pool2d(x, kernel_size=8)
        # 1 x 1 x 2048
        # x = F.dropout(x, training=self.training)
        # 1 x 1 x 2048
        x = x.view(x.size(0), -1)
        # 2048

        # global image features
        cnn_code = self.emb_cnn_code(x)
        # 512
        if features is not None:
            features = self.emb_features(features)

        # features of size: batch_size * embedding_size * 17 * 17
        # cnn_code of size: batch_size * embedding_size
        return features, cnn_code


class DAMSM_RNN_Encoder(BaseModel):
    def __init__(self,
                 vocab_size,
                 word_embed_size=256,
                 lstm_hidden_size=256,
                 lstm_num_layers=1,
                 drop_prob=0.5,
                 bidirectional=True):

        super(DAMSM_RNN_Encoder, self).__init__()

        self.vocab_size = vocab_size
        self.word_embed_size = word_embed_size
        self.lstm_hidden_size = lstm_hidden_size
        self.lstm_num_layers = lstm_num_layers
        self.drop_prob = drop_prob
        self.bidirectional = bidirectional

        if bidirectional:
            self.num_directions = 2
        else:
            self.num_directions = 1
        # number of features in the hidden state
        self.lstm_hidden_size = lstm_hidden_size // self.num_directions

        self.define_module()
        self.init_weights()

    def define_module(self):
        self.embedding = nn.Embedding(self.vocab_size, self.word_embed_size)  # embedding layer
        self.drop = nn.Dropout(self.drop_prob)
        # dropout: If non-zero, introduces a dropout layer on
        # the outputs of each RNN layer except the last layer
        self.lstm = nn.LSTM(self.word_embed_size,
                           self.lstm_hidden_size,
                           self.lstm_num_layers,
                           batch_first=True,
                           bidirectional=self.bidirectional)

    def init_weights(self):
        initrange = 0.1
        self.embedding.weight.data.uniform_(-initrange, initrange)
        # Do not need to initialize RNN parameters, which have been initialized
        # http://pytorch.org/docs/master/_modules/torch/nn/modules/rnn.html#LSTM
        # self.decoder.weight.data.uniform_(-initrange, initrange)
        # self.decoder.bias.data.fill_(0)

    def init_hidden(self, bsz):
        weight = next(self.parameters()).data
        if torch.cuda.is_available():
            return (Variable(weight.new(self.lstm_num_layers * self.num_directions,
                                        bsz, self.lstm_hidden_size).zero_()).cuda(),
                    Variable(weight.new(self.lstm_num_layers * self.num_directions,
                                        bsz, self.lstm_hidden_size).zero_()).cuda())
        else:
            return (Variable(weight.new(self.lstm_num_layers * self.num_directions,
                                        bsz, self.lstm_hidden_size).zero_()),
                    Variable(weight.new(self.lstm_num_layers * self.num_directions,
                                        bsz, self.lstm_hidden_size).zero_()))

    def forward(self, captions, caption_lengths, states=None):
        # input: torch.LongTensor of size batch x n_steps
        # --> emb: batch x n_steps x ninput
        if torch.cuda.is_available():
            self.lstm.flatten_parameters()

        total_length = captions.size(1)
        emb = self.drop(self.embedding(captions))
        #
        caption_lengths = caption_lengths.to('cpu').tolist()

        emb = pack_padded_sequence(emb, caption_lengths, batch_first=True)
        # #hidden and memory (num_layers * num_directions, batch, hidden_size):
        # tensor containing the initial hidden state for each element in batch.
        # #output (batch, seq_len, hidden_size * num_directions)
        # #or a PackedSequence object:
        # tensor containing output features (h_t) from the last layer of RNN
        output, hidden = self.lstm(emb, states)
        # PackedSequence object
        # --> (batch, seq_len, hidden_size * num_directions)
        output = pad_packed_sequence(output, batch_first=True, total_length=total_length)[0]
        # output = self.drop(output),
        # --> batch x hidden_size*num_directions x seq_len
        words_emb = output.transpose(1, 2)
        # --> batch x num_directions*hidden_size
        sent_emb = hidden[0].transpose(0, 1).contiguous()
        sent_emb = sent_emb.view(-1, self.lstm_hidden_size * self.num_directions)
        return words_emb, sent_emb