import torch
from torch.utils.data import DataLoader
from torchvision import transforms
from data_loader.datasets_custom import TextImageDataset, CaptionDataset, COCOCaptionDataset, COCOTextImageDataset
from base import BaseDataLoader


def text_image_collate_fn(data):
    collate_data = {}
    # Sort a data list by right caption length (descending order).
    data.sort(key=lambda x: x['right_caption'].size(0), reverse=True)

    collate_data['right_img_id'] = []
    # collate_data['class_id'] = []
    collate_data['right_txt'] = []
    right_captions = []
    right_embeds = []
    right_images_32 = []
    right_images_64 = []
    right_images_128 = []
    right_images_256 = []

    collate_data['wrong_img_id'] = []
    collate_data['wrong_txt'] = []
    wrong_captions = []
    wrong_embeds = []
    wrong_images_32 = []
    wrong_images_64 = []
    wrong_images_128 = []
    wrong_images_256 = []

    for i in range(len(data)):
        collate_data['right_img_id'].append(data[i]['right_img_id'])
        # collate_data['class_id'].append(data[i]['right_image_class_id'])
        collate_data['right_txt'].append(data[i]['right_txt'])
        right_captions.append(data[i]['right_caption'])
        right_embeds.append(data[i]['right_embed'])
        right_images_32.append(data[i]['right_image_32'])
        right_images_64.append(data[i]['right_image_64'])
        right_images_128.append(data[i]['right_image_128'])
        right_images_256.append(data[i]['right_image_256'])

        collate_data['wrong_img_id'].append(data[i]['wrong_img_id'])
        collate_data['wrong_txt'].append(data[i]['wrong_txt'])
        wrong_captions.append(data[i]['wrong_caption'])
        wrong_embeds.append(data[i]['wrong_embed'])
        wrong_images_32.append(data[i]['wrong_image_32'])
        wrong_images_64.append(data[i]['wrong_image_64'])
        wrong_images_128.append(data[i]['wrong_image_128'])
        wrong_images_256.append(data[i]['wrong_image_256'])

    # sort and get captions, lengths, images, embeds, etc.
    right_caption_lengths = [len(cap) for cap in right_captions]
    collate_data['right_caption_lengths'] = right_caption_lengths
    collate_data['right_captions'] = torch.zeros(len(right_caption_lengths), max(right_caption_lengths)).long()
    for i, cap in enumerate(right_captions):
        end = right_caption_lengths[i]
        collate_data['right_captions'][i, :end] = cap[:end]

    # sort and get captions, lengths, images, embeds, etc.
    wrong_captions.sort(key=lambda x: len(x), reverse=True)
    wrong_caption_lengths = [len(cap) for cap in wrong_captions]
    collate_data['wrong_caption_lengths'] = wrong_caption_lengths
    collate_data['wrong_captions'] = torch.zeros(len(wrong_caption_lengths), max(wrong_caption_lengths)).long()
    for i, cap in enumerate(wrong_captions):
        end = wrong_caption_lengths[i]
        collate_data['wrong_captions'][i, :end] = cap[:end]

    collate_data['right_embeds'] = torch.stack(right_embeds, 0)
    collate_data['right_images_32'] = torch.stack(right_images_32, 0)
    collate_data['right_images_64'] = torch.stack(right_images_64, 0)
    collate_data['right_images_128'] = torch.stack(right_images_128, 0)
    collate_data['right_images_256'] = torch.stack(right_images_256, 0)

    collate_data['wrong_embeds'] = torch.stack(wrong_embeds, 0)
    collate_data['wrong_images_32'] = torch.stack(wrong_images_32, 0)
    collate_data['wrong_images_64'] = torch.stack(wrong_images_64, 0)
    collate_data['wrong_images_128'] = torch.stack(wrong_images_128, 0)
    collate_data['wrong_images_256'] = torch.stack(wrong_images_256, 0)

    return collate_data


def image_caption_collate_fn(data):
    # sort the data in descentding order
    data.sort(key=lambda  x: len(x[-1]), reverse=True)
    image_ids, images, captions = zip(*data)

    # merge images (from tuple of 1D tensor to 4D tensor)
    batch_images = torch.stack(images, 0)
    # batch_image_ids = torch.stack(image_ids, 0)
    batch_image_ids = image_ids
    # batch_class_ids = class_ids

    # merge captions (from tuple of 1D tensor to 2D tensor)
    batch_caption_lengths = [len(cap) for cap in captions]
    batch_captions = torch.zeros(len(captions), max(batch_caption_lengths)).long()
    for i, cap in enumerate(captions):
        end = batch_caption_lengths[i]
        batch_captions[i, :end] = cap[:end]

    return batch_image_ids, batch_images, batch_captions, batch_caption_lengths


class COCOCaptionDataLoader(BaseDataLoader):
    """
    COCO Image Caption Model Data Loader
    """
    def __init__(self, data_dir, which_set, image_size, batch_size, validation_split, num_workers):

        self.data_dir = data_dir
        self.which_set = which_set
        self.validation_split = validation_split
        assert self.which_set in {'train', 'val', 'test'}

        self.image_size = (image_size, image_size)
        self.batch_size = batch_size
        self.num_workers = num_workers

        # transforms.ToTensor convert PIL images in range [0, 255] to a torch in range [0.0, 1.0]
        mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32)
        std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32)

        if which_set == 'val' or which_set == 'test':
            self.transform = transforms.Compose([
                transforms.Resize(self.image_size),
                # transforms.RandomHorizontalFlip(),
                # transforms.CenterCrop(224),
                transforms.ToTensor(),
                transforms.Normalize(mean=mean.tolist(), std=std.tolist())
            ])
        else:
            self.transform = transforms.Compose([
                transforms.Resize(self.image_size),
                transforms.RandomHorizontalFlip(),
                transforms.ToTensor(),
                transforms.Normalize(mean=mean.tolist(), std=std.tolist())
            ])

        self.dataset = COCOCaptionDataset(self.data_dir, self.which_set, self.transform, vocab_from_file=True)
        # self.n_samples = len(self.dataset)

        if self.which_set == 'train':
            super(COCOCaptionDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=True,
                validation_split=validation_split,
                num_workers=self.num_workers,
                collate_fn=image_caption_collate_fn
            )
        else:
            super(COCOCaptionDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=False,
                validation_split=0,
                num_workers=self.num_workers,
                collate_fn=image_caption_collate_fn)


class CaptionDataLoader(DataLoader):
    """
    CUB (Birds) Image Captioning Data Loader
    """
    def __init__(self, data_dir, dataset_name, which_set, image_size, batch_size, num_workers):

        self.data_dir = data_dir
        self.which_set = which_set
        self.dataset_name = dataset_name
        assert self.which_set in {'train', 'valid', 'test'}

        self.image_size = (image_size, image_size)
        self.batch_size = batch_size
        self.num_workers = num_workers

        # transforms.ToTensor convert PIL images in range [0, 255] to a torch in range [0.0, 1.0]
        if which_set == 'valid' or which_set == 'test':
            self.transform = transforms.Compose([
                transforms.Resize(self.image_size),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])
        else:
            self.transform = transforms.Compose([
                transforms.Resize(self.image_size),
                transforms.RandomHorizontalFlip(),
                transforms.ToTensor(),
                transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
            ])

        self.dataset = CaptionDataset(self.data_dir, self.dataset_name, self.which_set, self.transform, vocab_from_file=False)
        self.n_samples = len(self.dataset)

        if self.which_set == 'train' or self.which_set == 'valid':
            super(CaptionDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=True,
                num_workers=self.num_workers,
                collate_fn=image_caption_collate_fn
            )
        else:
            super(CaptionDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=False,
                num_workers=0,
                collate_fn=image_caption_collate_fn)


class TextImageDataLoader(DataLoader):
    def __init__(self, data_dir, dataset_name, which_set, image_size, batch_size, num_workers):
        self.data_dir = data_dir
        self.which_set = which_set
        self.dataset_name = dataset_name
        assert self.which_set in {'train', 'valid', 'test'}

        self.image_size = (image_size, image_size)
        self.batch_size = batch_size
        self.num_workers = num_workers

        # transforms.ToTensor convert PIL images in range [0, 255] to a torch in range [0.0, 1.0]
        self.transform = transforms.Compose([
            transforms.RandomHorizontalFlip(),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

        self.dataset = TextImageDataset(self.data_dir, self.dataset_name, self.which_set, self.transform, vocab_from_file=False)
        self.n_samples = len(self.dataset)

        if self.which_set == 'train' or self.which_set == 'valid':
            super(TextImageDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=True,
                num_workers=self.num_workers,
                collate_fn=text_image_collate_fn
            )
        else:
            super(TextImageDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=False,
                num_workers=0,
                collate_fn=text_image_collate_fn)


class COCOTextImageDataLoader(BaseDataLoader):
    """
    COCO Image Caption Model Data Loader
    """
    def __init__(self, data_dir, which_set, image_size, batch_size, validation_split, num_workers):

        self.data_dir = data_dir
        self.which_set = which_set
        self.validation_split = validation_split
        assert self.which_set in {'train', 'val', 'test'}

        self.image_size = (image_size, image_size)
        self.batch_size = batch_size
        self.num_workers = num_workers

        # transforms.ToTensor convert PIL images in range [0, 255] to a torch in range [0.0, 1.0]
        mean = torch.tensor([0.485, 0.456, 0.406], dtype=torch.float32)
        std = torch.tensor([0.229, 0.224, 0.225], dtype=torch.float32)

        if which_set == 'val' or which_set == 'test':
            self.transform = transforms.Compose([
                transforms.RandomHorizontalFlip(),
                transforms.ToTensor(),
                transforms.Normalize(mean=mean, std=std)
            ])
        else:
            self.transform = transforms.Compose([
                # transforms.RandomHorizontalFlip(),
                transforms.ToTensor(),
                transforms.Normalize(mean=mean, std=std)
            ])

        self.dataset = COCOTextImageDataset(self.data_dir, self.which_set, self.transform, vocab_from_file=True)
        # self.n_samples = len(self.dataset)

        if self.which_set == 'train':
            super(COCOTextImageDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=True,
                validation_split=validation_split,
                num_workers=self.num_workers,
                collate_fn=text_image_collate_fn
            )
        else:
            super(COCOTextImageDataLoader, self).__init__(
                dataset=self.dataset,
                batch_size=self.batch_size,
                shuffle=False,
                validation_split=0,
                num_workers=self.num_workers,
                collate_fn=text_image_collate_fn)


if __name__ == '__main__':
    data_loader = COCOCaptionDataLoader(
        data_dir='/Users/leon/Projects/I2T2I/data/coco/',
        # dataset_name="flowers",
        which_set='train',
        image_size=128,
        batch_size=16,
        num_workers=0,
        validation_split=0)

    print(len(data_loader.dataset.vocab))
    print(data_loader.dataset.vocab.word2idx)

    for i, (images, captions, caption_lengths) in enumerate(data_loader):
        print("done")

        print('images.shape:', images.shape)
        print('captions.shape:', captions.shape)

        # Print the pre-processed images and captions.
        print('images:', images)
        print('captions:', captions)

        break



        