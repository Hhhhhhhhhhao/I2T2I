import torch
import torch.nn as nn
import torch.nn.functional as F
import torchvision
import numpy as np
from torch.nn.utils.rnn import pack_padded_sequence
from base import BaseModel


device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


class MnistModel(BaseModel):
    def __init__(self, num_classes=10):
        super(MnistModel, self).__init__()
        self.conv1 = nn.Conv2d(1, 10, kernel_size=5)
        self.conv2 = nn.Conv2d(10, 20, kernel_size=5)
        self.conv2_drop = nn.Dropout2d()
        self.fc1 = nn.Linear(320, 50)
        self.fc2 = nn.Linear(50, num_classes)

    def forward(self, x):
        x = F.relu(F.max_pool2d(self.conv1(x), 2))
        x = F.relu(F.max_pool2d(self.conv2_drop(self.conv2(x)), 2))
        x = x.view(-1, 320)
        x = F.relu(self.fc1(x))
        x = F.dropout(x, training=self.training)
        x = self.fc2(x)
        return F.log_softmax(x, dim=1)


class EncoderCNN(BaseModel):
    """
    Encoder
    """

    def __init__(self, image_embed_size=256):
        super(EncoderCNN, self).__init__()

        adaptive_pool_size = 4
        resnet = torchvision.models.resnet34(pretrained=True)

        # Remove average pooling layers
        modules = list(resnet.children())[:-2]
        self.resnet = nn.Sequential(*modules)
        self.adaptive_pool = nn.AdaptiveAvgPool2d((adaptive_pool_size, adaptive_pool_size))
        self.fc_in_features = 512 * adaptive_pool_size ** 2
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
        for c in list(self.resnet.children())[7:]:
            for p in c.parameters():
                p.requires_grad = fine_tune


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
        """
        Decode image feature vectors and generate captions.

        :param features: encoded images, a tensor of dimension (batch_size, encoded_image_size, encoded_image_size, 2048)
        :param captions: encoded captions, a tensor of dimension (batch_size, max_caption_length)
        :param caption_lengths: caption lengths, a tensor of dimension (batch_size, 1)
        :return: scores of vocabulary, sorted encoded captions, decode lengths, weights, sort indices
        """
        # Embedding
        embeddings = self.embedding(captions)  # (batch_size, max_caption_length, embed_dim)
        embeddings = torch.cat((features.unsqueeze(1), embeddings), 1)
        packed = pack_padded_sequence(embeddings, caption_lengths, batch_first=True)
        hiddens, _ = self.lstm(packed)
        outputs = self.linear(hiddens[0])
        return outputs

    def sample(self, features, max_len=20, states=None):
        """
        Sample from Recurrent network using greedy decoding
        :param features: features from CNN feature extractor
        :returns: predicted image captions
        """
        output_ids = []
        inputs = features.unsqueeze(1)

        for i in range(max_len):
            # pass data through recurrent network
            hiddens, states = self.lstm(inputs, states)
            outputs = self.linear(hiddens.squeeze(1))

            # find maximal predictions
            predicted = outputs.max(1)[1]

            # append results from given step to global results
            output_ids.append(predicted)

            # prepare chosen words for next decoding step
            inputs = self.embedding(predicted)
            inputs = inputs.unsqueeze(1)
        output_ids = torch.stack(output_ids, 1)
        return output_ids.squeeze()

    def sample_beam_search(self, features, max_len=20, beam_width=5, states=None):
        """Accept a pre-processed image tensor and return the top predicted
        sentences. This is the beam search approach.
        """
        # Top word idx sequences and their corresponding inputs and states
        inputs = features.unsqueeze(1)
        idx_sequences = [[[], 0.0, inputs, states]]
        for _ in range(max_len):
            # Store all the potential candidates at each step
            all_candidates = []
            # Predict the next word idx for each of the top sequences
            for idx_seq in idx_sequences:
                hiddens, states = self.lstm(idx_seq[2], idx_seq[3])
                outputs = self.linear(hiddens.squeeze(1))
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
                    inputs = self.embedding(top_idx[i].unsqueeze(0)).unsqueeze(0)
                    all_candidates.append([next_idx_seq, log_prob, inputs, states])
            # Keep only the top sequences according to their total log probability
            ordered = sorted(all_candidates, key=lambda x: x[1], reverse=True)
            idx_sequences = ordered[:beam_width]
        return [idx_seq[0] for idx_seq in idx_sequences]


class ImageCaptionModel(BaseModel):
    def __init__(self, image_embed_size, word_embed_size, lstm_hidden_size, vocab_size, lstm_num_layers=1):
        super(ImageCaptionModel, self).__init__()
        self.image_embed_size = image_embed_size
        self.word_embed_size = word_embed_size
        self.lstm_hidden_size = lstm_hidden_size
        self.lstm_num_layers = lstm_num_layers
        self.vocab_size = vocab_size

        self.encoder = EncoderCNN(self.image_embed_size)
        self.decoder = DecoderRNN(self.word_embed_size, self.lstm_hidden_size, self.vocab_size, self.lstm_num_layers)

    def forward(self, images, captions, caption_lengths):
        features = self.encoder(images)
        outputs = self.decoder(features, captions, caption_lengths)
        return outputs

    def sample(self, features, max_len=20, states=None):
        return self.decoder.sample(features, max_len, states)

    def sample_beam_search(self, features, max_len=20, beam_width=5, states=None):
        return self.decoder.sample_beam_search(features, max_len, beam_width, states)


if __name__ == '__main__':
    from data_loader import COCOCaptionDataLoader
    from torchsummary import summary

    image_size = 128
    batch_size = 16

    # data_loader = COCOCaptionDataLoader(
    #     data_dir='/Users/leon/Projects/I2T2I/data/coco/',
    #     which_set='val',
    #     image_size=image_size,
    #     batch_size=batch_size,
    #     num_workers=0,
    #     validation_split=0)
    #
    # for i, (image_ids, images, captions, caption_lengths) in enumerate(data_loader):
    #     print("done")
    #     break
    #
    # print('images.shape:', images.shape)
    # print('captions.shape:', captions.shape)
    #
    # # Test Encoder
    # embed_size = 256   # dimensionality of the image embedding.
    #
    # # Move the last batch of images from Step 2 to GPU if CUDA is available
    # if torch.cuda.is_available():
    #     images = images.cuda()
    #
    # # Test Decoder
    # hidden_size = 512
    # vocab_size = len(data_loader.dataset.vocab)
    #
    # # Move the last batch of captions (from Step 1) to GPU if cuda is availble
    # if torch.cuda.is_available():
    #     captions = captions.cuda()
    #
    # # test the whole model
    embed_size = 256
    hidden_size = 512
    vocab_size = 10330
    model = ImageCaptionModel(4, embed_size, embed_size, hidden_size, vocab_size)
    # summary(model, input_size=(3, 256, 256))
    # Move the decoder to GPU if CUDA is available.
    if torch.cuda.is_available():
        model = model.cuda()
    #
    # outputs = model(images, captions, caption_lengths)
    # print('type(features):', type(outputs))
    # print('features.shape:', outputs.shape)





