import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
from torch.distributions import Normal
from torch.autograd import Variable
from torch.nn.utils.rnn import pack_padded_sequence, pad_packed_sequence
from base import BaseModel
from model.rollout_module import Rollout

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class EncoderCNN(BaseModel):
    """
    Encoder
    """

    def __init__(self, image_embed_size=256):
        super(EncoderCNN, self).__init__()

        adaptive_pool_size = 12
        resnet = torchvision.models.resnet34(pretrained=True)

        # Remove average pooling layers
        modules = list(resnet.children())[:-3]
        self.resnet = nn.Sequential(*modules)
        self.adaptive_pool = nn.AdaptiveAvgPool2d((adaptive_pool_size, adaptive_pool_size))
        self.fc_in_features = 256 * adaptive_pool_size ** 2
        self.linear = nn.Linear(self.fc_in_features, image_embed_size)
        self.init_weights()
        self.fine_tune()

    def init_weights(self):
        self.linear.weight.data.normal_(0.0, 0.01)
        self.linear.bias.data.fill_(0)

    def forward(self, images):
        """
        Forward propagation.
        :param images: images, a tensor of dimensions (batch_size, 3, image_size, image_size)
        :return: encoded images
        """

        features = self.resnet(images)
        features = self.adaptive_pool(features)
        features = features.view(features.size(0), -1)
        features = self.linear(features)

        return features

    def fine_tune(self, fine_tune=True):
        """
        Allow or prevent the computation of gradients for convolutional blocks 2 through 4 of the encoder.
        :param fine_tune:
        """

        for p in self.resnet.parameters():
            p.requires_grad = False
        # If fine-tuning, only fine tune convolutional blocks 2 through 4
        for c in list(self.resnet.children())[4:]:
            for p in c.parameters():
                p.requires_grad = fine_tune


class EncoderRNN(BaseModel):
    def __init__(self, word_embed_size, sentence_embed_size, lstm_hidden_size, vocab_size, num_layers=1):
        """
        Set the hyper-parameters and build the layers.
        :param embed_size: word embedding size
        :param hidden_size: hidden unit size of LSTM
        :param vocab_size: size of vocabulary (output of the network)
        :param num_layers:
        :param dropout: use of drop out
        """
        super(EncoderRNN, self).__init__()
        self.word_embed_size = word_embed_size
        self.lstm_hidden_size = lstm_hidden_size
        self.vocab_size = vocab_size
        self.sentence_embed_size = sentence_embed_size

        self.embedding = nn.Embedding(vocab_size, word_embed_size)  # embedding layer
        self.lstm = nn.LSTM(word_embed_size, lstm_hidden_size, num_layers, bias=True, batch_first=True)
        self.linear = nn.Linear(lstm_hidden_size, sentence_embed_size)  # linear layer to find scores over vocabulary
        # self.activation = nn.LeakyReLU(0.2)
        self.init_weights()

    def init_weights(self):
        """
        Initializes some parameters with values from the uniform distribution, for easier convergence.
        """
        self.embedding.weight.data.uniform_(-0.1, 0.1)
        self.linear.bias.data.fill_(0)
        self.linear.weight.data.uniform_(-0.1, 0.1)

    def forward(self, captions, caption_lengths):
        """
        Decode image feature vectors and generate captions.
        :param features: encoded images, a tensor of dimension (batch_size, encoded_image_size, encoded_image_size, 2048)
        :param captions: encoded captions, a tensor of dimension (batch_size, max_caption_length)
        :param caption_lengths: caption lengths, a tensor of dimension (batch_size, 1)
        :return: scores of vocabulary, sorted encoded captions, decode lengths, weights, sort indices
        """
        self.lstm.flatten_parameters()
        # Embedding
        embeddings = self.embedding(captions)  # (batch_size, max_caption_length, embed_dim)
        caption_lengths = caption_lengths.to("cpu").tolist()
        total_length = captions.size(1)
        packed = pack_padded_sequence(embeddings, caption_lengths, batch_first=True)
        hiddens, _ = self.lstm(packed)
        # print("hiddens shape {}".format(hiddens[0].shape))
        padded = pad_packed_sequence(hiddens, batch_first=True, total_length=total_length)
        last_padded_indices = [index-1 for index in padded[1]]
        hidden_outputs = padded[0][range(captions.size(0)), last_padded_indices, :]
        # print("hidden_outputs shape:{}".format(hidden_outputs.shape))
        outputs = self.linear(hidden_outputs)
        # outputs = self.activation(outputs)
        return outputs


class DecoderRNN(BaseModel):
    def __init__(self, word_embed_size, lstm_hidden_size, vocab_size, num_layers=1):
        """
        Set the hyper-parameters and build the layers.
        :param embed_size: word embedding size
        :param hidden_size: hidden unit size of LSTM
        :param vocab_size: size of vocabulary (output of the network)
        :param num_layers:
        :param dropout: use of drop out
        """
        super(DecoderRNN, self).__init__()
        self.word_embed_size = word_embed_size
        self.lstm_hidden_size = lstm_hidden_size
        self.vocab_size = vocab_size

        self.embedding = nn.Embedding(vocab_size, word_embed_size) # embedding layer
        self.lstm = nn.LSTM(word_embed_size, lstm_hidden_size, num_layers, bias=True, batch_first=True)
        self.linear = nn.Linear(lstm_hidden_size, vocab_size)   # linear layer to find scores over vocabulary
        self.init_weights()

    def init_weights(self):
        """
        Initializes some parameters with values from the uniform distribution, for easier convergence.
        """
        self.embedding.weight.data.uniform_(-0.1, 0.1)
        self.linear.bias.data.fill_(0)
        self.linear.weight.data.uniform_(-0.1, 0.1)

    def forward(self, features, captions, caption_lengths):
        # states include features extracted from image and noise, also initial cell state
        # Embedding
        embeddings = self.embedding(captions)  # (batch_size, max_caption_length, embed_dim)
        embeddings = torch.cat((features.unsqueeze(1), embeddings), 1)
        caption_lengths = caption_lengths.to("cpu").tolist()
        packed = pack_padded_sequence(embeddings, caption_lengths, batch_first=True)
        hiddens, _ = self.lstm(packed)
        outputs = self.linear(hiddens[0])
        return outputs


class ConditionalGenerator(BaseModel):

    def __init__(self,
                 image_embed_size=256,
                 word_embed_size=256,
                 lstm_hidden_size=256,
                 noise_dim=100,
                 vocab_size=10000,
                 lstm_num_layers=1,
                 max_sentence_length=20):
        super(ConditionalGenerator, self).__init__()
        self.image_embed_size =image_embed_size
        self.word_embed_size = word_embed_size
        self.lstm_hidden_size = lstm_hidden_size
        self.lstm_num_layers = lstm_num_layers
        self.vocab_size = vocab_size
        self.max_sentence_length = max_sentence_length
        # noise variable
        self.distribution = Normal(Variable(torch.zeros(noise_dim)), Variable(torch.ones(noise_dim)))

        # image feature encoder
        self.encoder = EncoderCNN(self.image_embed_size)
        self.features_linear = nn.Sequential(nn.Linear(self.image_embed_size + noise_dim, self.image_embed_size), nn.LeakyReLU(0.2))
        self.decoder = DecoderRNN(self.word_embed_size, self.lstm_hidden_size, self.vocab_size, self.lstm_num_layers)
        self.rollout = Rollout(max_sentence_length)

    def init_features(self, image_features):
        # generate rand
        rand = self.distribution.sample((image_features.shape[0],))
        rand = rand.to(device)

        # hidden of shape (num_layers * num_directions, batch, hidden_size)
        features = self.features_linear(torch.cat((image_features, rand), 1))
        features = features.to(device)

        # # cell of shape (num_layers * num_directions, batch, hidden_size)
        # cell = Variable(torch.zeros(image_features.shape[0], self.image_embed_size).unsqueeze(0))
        # cell = cell.to(device)

        return features

    def forward(self, images, captions, caption_lengths):
        image_features = self.encoder(images)
        features = self.init_features(image_features)
        outputs = self.decoder(features, captions, caption_lengths)
        # return input featuers to LSTM and outputs from LSTM
        return image_features, features, outputs

    def feature_forward(self, images):
        image_features = self.encoder(images)
        features = self.init_features(image_features)
        return features

    def reward_forward(self, images, evaluator, monte_carlo_count=18):
        '''
        :param image: image features from image encoder linear layer
        :param evaluator: evaluator model
        :param monte_carlo_count: monte carlo count
        :return:
        '''
        batch_size = images.size(0)
        image_features = self.encoder(images)
        features = self.init_features(image_features)

        # initialize inputs of start symbol
        # h = features.unsqueeze(0)
        # c = Variable(torch.zeros(batch_size, self.image_embed_size).unsqueeze(0)).to(device)
        # states = h, c
        #
        # inputs = torch.zeros(batch_size, 1).long()
        # current_generated_captions = inputs
        # inputs = self.decoder.embedding(inputs.to(device))

        # inputs = features.unsqueeze(1)
        # states = None
        # current_generated_captions = None

        # inputs = torch.zeros(batch_size, 1).long()
        # current_generated_captions = inputs
        # inputs = self.decoder.embedding(inputs.to(device))
        # _, states = self.decoder.lstm(features.unsqueeze(1))

        inputs = torch.zeros(batch_size, 1).long()
        current_generated_captions = inputs
        inputs = self.decoder.embedding(inputs.to(device))
        _, states = self.decoder.lstm(features.unsqueeze(1))

        rewards = torch.zeros(batch_size, self.max_sentence_length)
        rewards = rewards.to(device)
        props = torch.zeros(batch_size, self.max_sentence_length)
        props = props.to(device)

        self.rollout.update(self)

        for i in range(self.max_sentence_length):

            hiddens, states = self.decoder.lstm(inputs, states)
            # squeeze the hidden output size from (batch_siz, 1, hidden_size) to (batch_size, hidden_size)
            outputs = self.decoder.linear(hiddens.squeeze(1))

            # outputs of size (batch_size, vocab_size)
            outputs = F.softmax(outputs, -1)

            #
            # if current_generated_captions is None:
            # predicted = outputs.argmax(1)
            # predicted = (predicted.unsqueeze(1)).long()
            #     current_generated_captions = predicted.cpu()
            # else:
            predicted = outputs.multinomial(1)
            current_generated_captions = torch.cat([current_generated_captions, predicted.cpu()], dim=1)

            # if torch.cuda.is_available():
            #   predicted = predicted.cuda()
            prop = torch.gather(outputs, 1, predicted)
            # prop is a 1D tensor
            props[:, i] = prop.view(-1)

            # embed the next inputs, unsqueeze is required cause of shape (batch_size, vocab_size)
            # if current_generated_captions is None:
            #     current_generated_captions = predicted.cpu()
            # else:
            # current_generated_captions = torch.cat([current_generated_captions, predicted.cpu()], dim=1)

            inputs = self.decoder.embedding(predicted)

            reward = self.rollout.reward(images, current_generated_captions, states, monte_carlo_count, evaluator)
            rewards[:, i] = reward.view(-1)

        return rewards, props

    def feature_to_text(self, features, max_len=20):
        generated_captions = []
        for feature in features:
            generated_captions.append(self.sample(feature.unsqueeze(0), states=None, max_len=max_len))
        return generated_captions

    def sample(self, features, states=None, max_len=20):
        """Accept a pre-processed image tensor (inputs) and return predicted
        sentence (list of tensor ids of length max_len). This is the greedy
        search approach.
        """
        sampled_ids = []
        inputs = features.unsqueeze(1)
        for i in range(max_len):
            hiddens, states = self.decoder.lstm(inputs, states)  # (batch_size, 1, hidden_size)
            outputs = self.decoder.linear(hiddens.squeeze(1))  # (batch_size, vocab_size)
            # Get the index (in the vocabulary) of the most likely integer that
            # represents a word
            predicted = outputs.argmax(1)
            sampled_ids.append(predicted.item())
            inputs = self.decoder.embedding(predicted)
            inputs = inputs.unsqueeze(1)
        return sampled_ids

    def sample_beam_search(self, features, max_len=20, beam_width=3, states=None):
        """Accept a pre-processed image tensor and return the top predicted
        sentences. This is the beam search approach.
        """
        # Top word idx sequences and their corresponding inputs and states
        inputs = features.transpose(1, 0, 2)
        idx_sequences = [[[], 0.0, inputs, states]]
        for _ in range(max_len):
            # Store all the potential candidates at each step
            all_candidates = []
            # Predict the next word idx for each of the top sequences
            for idx_seq in idx_sequences:
                hiddens, states = self.decoder.lstm(idx_seq[2], idx_seq[3])
                outputs = self.decoder.linear(hiddens.squeeze(1))
                # Transform outputs to log probabilities to avoid floating-point
                # underflow caused by multiplying very small probabilities
                log_probs = F.log_softmax(outputs, -1)
                top_log_probs, top_idx = log_probs.topk(beam_width, 1)
                top_idx = top_idx.squeeze(0)
                # create a new set of top sentences for next round
                for i in range(beam_width):
                    next_idx_seq, log_prob = idx_seq[0][:], idx_seq[1]
                    next_idx_seq.append(top_idx[i].item())
                    log_prob += top_log_probs[0][i].item()
                    # Indexing 1-dimensional top_idx gives 0-dimensional tensors.
                    # We have to expand dimensions before embedding them
                    inputs = self.decoder.embedding(top_idx[i].unsqueeze(0)).unsqueeze(0)
                    all_candidates.append([next_idx_seq, log_prob, inputs, states])
            # Keep only the top sequences according to their total log probability
            ordered = sorted(all_candidates, key=lambda x: x[1], reverse=True)
            idx_sequences = ordered[:beam_width]
        return [idx_seq[0] for idx_seq in idx_sequences]


class Evaluator(BaseModel):
    def __init__(self,
                 word_embed_size=256,
                 sentence_embed_size=256,
                 lstm_hidden_size=256,
                 vocab_size=100000,
                 lstm_num_layers=1):
        super(Evaluator, self).__init__()
        self.word_embed_size = word_embed_size
        self.lstm_hidden_size = lstm_hidden_size
        self.vocab_size = vocab_size
        self.sentence_embed_size = sentence_embed_size

        self.embedding = nn.Embedding(vocab_size, self.word_embed_size)  # embedding layer
        self.lstm = nn.LSTM(self.word_embed_size, self.lstm_hidden_size, num_layers=lstm_num_layers, bias=True, batch_first=True)
        self.linear = nn.Linear(lstm_hidden_size, sentence_embed_size)  # linear layer to find scores over vocabulary
        self.init_weights()
        self.sigmoid = nn.Sigmoid()
        # self.output_linear = nn.Linear(1, 1)
        self.cnn_encoder = EncoderCNN(image_embed_size=sentence_embed_size)

    def init_weights(self):
        """
        Initializes some parameters with values from the uniform distribution, for easier convergence.
        """
        self.embedding.weight.data.uniform_(-0.1, 0.1)
        self.linear.bias.data.fill_(0)
        self.linear.weight.data.uniform_(-0.1, 0.1)

    def forward(self, images, captions, caption_lengths):
        """ Calculate reward score: r = logistic(dot_prod(f, h))"""

        image_features = self.cnn_encoder(images)

        if image_features.size(0) != captions.size(0):
            monte_carlo_count = int(captions.size(0) / image_features.size(0))
            image_features = image_features.repeat(monte_carlo_count, 1)

        # Embedding
        embeddings = self.embedding(captions)  # (batch_size, max_caption_length, embed_dim)
        caption_lengths = caption_lengths.to("cpu").tolist()
        total_length = captions.size(1)
        packed = pack_padded_sequence(embeddings, caption_lengths, batch_first=True)
        hiddens, _ = self.lstm(packed)
        # print("hiddens shape {}".format(hiddens[0].shape))
        padded = pad_packed_sequence(hiddens, batch_first=True, total_length=total_length)
        last_padded_indices = [index-1 for index in padded[1]]
        hidden_outputs = padded[0][range(captions.size(0)), last_padded_indices, :]
        # print("hidden_outputs shape:{}".format(hidden_outputs.shape))
        sentence_features = self.linear(hidden_outputs)

        dot_product = torch.bmm(image_features.unsqueeze(1), sentence_features.unsqueeze(1).transpose(2,1))
        dot_product = dot_product.unsqueeze(-1)
        # similarity = self.output_linear(dot_product)
        similarity = self.sigmoid(dot_product)

        # similarity = similarity
        return similarity
