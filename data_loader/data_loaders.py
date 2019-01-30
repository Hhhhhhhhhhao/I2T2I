import os
import h5py
import json
import torch
from torch.utils.data import DataLoader, sampler
from torchvision import datasets, transforms
from base import BaseDataLoader
from datasets_custom import COCOCaptionDataset


class MnistDataLoader(BaseDataLoader):
    """
    MNIST data loading demo using BaseDataLoader
    """
    def __init__(self, data_dir, batch_size, shuffle, validation_split, num_workers, training=True):
        trsfm = transforms.Compose([
            transforms.ToTensor(),
            transforms.Normalize((0.1307,), (0.3081,))
            ])
        self.data_dir = data_dir
        self.dataset = datasets.MNIST(self.data_dir, train=training, download=True, transform=trsfm)
        super(MnistDataLoader, self).__init__(self.dataset, batch_size, shuffle, validation_split, num_workers)


class COCOCaptionDataLoader(DataLoader):
    """

    """
    def __init__(self, data_dir, which_set, image_size, batch_size, num_workers):

        self.data_dir = data_dir
        self.which_set = which_set
        assert self.which_set in {'train', 'val', 'test'}

        self.image_size = image_size
        self.batch_size = batch_size
        self.num_workers = num_workers

        self.transform = transforms.Compose([
            transforms.Resize(self.image_size),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        self.dataset = COCOCaptionDataset(self.data_dir, self.which_set, self.image_size, self.batch_size, self.transform)

        if self.which_set == 'train':
            # Randomly sample a caption length, and sample indices with that length.
            # indices = self.dataset.get_indices()
            # Create and assign a batch sampler to retrieve a batch with the sampled indices.
            # initial_sampler = sampler.SubsetRandomSampler(indices=indices)
            # data loader for COCO dataset.
            # super(COCOCaptionDataLoader, self).__init__(
            #     dataset=self.dataset,
            #     batch_sampler=initial_sampler,
            #     num_workers=self.num_workers,
            #     drop_last=False)
            super(COCOCaptionDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=True,
                num_workers=self.num_workers
            )
        else:
            super(COCOCaptionDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=True,
                num_workers=self.num_workers)


if __name__ == '__main__':
    import nltk

    data_loader = COCOCaptionDataLoader(
        data_dir='/Users/leon/Projects/I2T2I/data/coco/',
        which_set='train',
        image_size=(128, 128),
        batch_size=16,
        num_workers=0)

    sample_caption = 'A person doing a trick on a rail while riding a skateboard.'
    sample_tokens = nltk.tokenize.word_tokenize(str(sample_caption).lower())
    print(sample_tokens)

    sample_caption = []
    start_word = data_loader.dataset.vocab.start_word
    print('Special start word:', start_word)
    sample_caption.append(data_loader.dataset.vocab(start_word))
    print(sample_caption)

    sample_caption.extend([data_loader.dataset.vocab(token) for token in sample_tokens])
    print(sample_caption)

    end_word = data_loader.dataset.vocab.end_word
    print('Special end word:', end_word)

    sample_caption.append(data_loader.dataset.vocab(end_word))
    print(sample_caption)

    sample_caption = torch.Tensor(sample_caption).long()
    print(sample_caption)

    # Preview the word2idx dictionary.
    print(dict(list(data_loader.dataset.vocab.word2idx.items())[:10]))

    # Print the total number of keys in the word2idx dictionary.
    print('Total number of tokens in vocabulary:', len(data_loader.dataset.vocab))

    # Randomly sample a caption length, and sample indices with that length.
    indices = data_loader.dataset.get_indices()
    print('{} sampled indices: {}'.format(len(indices), indices))
    # Create and assign a batch sampler to retrieve a batch with the sampled indices.
    new_sampler = sampler.SubsetRandomSampler(indices=indices)
    data_loader.batch_sampler.sampler = new_sampler

    # batch = data_loader

    for batch in data_loader:
        images = batch[0]
        captions = batch[1]
        break

    images, captions = batch[0], batch[1]
    print('images.shape:', images.shape)
    print('captions.shape:', captions.shape)

    # Print the pre-processed images and captions.
    print('images:', images)
    print('captions:', captions)



        