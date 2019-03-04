from trainer.trainer_cls import Trainer
from torch.utils.data import DataLoader
from data_loader.txt2image_dataset import Text2ImageDataset_Origin
import datetime
import os
dirname = os.path.dirname(__file__)
data_dir = os.path.join(dirname, 'data')

from utils.arg_extractor import get_args

if __name__ == '__main__':

    args = get_args()

    if args.dataset_name == 'birds':

        train_data_loader = DataLoader(

            Text2ImageDataset_Origin(
                data_dir=data_dir,
                dataset_name="birds",
                which_set="train"
            ),

            batch_size=64,
            shuffle=True,
            num_workers=0
        )

        valid_data_loader = DataLoader(

            Text2ImageDataset_Origin(
                data_dir=data_dir,
                dataset_name="birds",
                which_set="train"
            ),

            batch_size=64,
            shuffle=False,
            num_workers=0
        )

    elif args.dataset_name == 'flowers':

        train_data_loader = DataLoader(

            Text2ImageDataset_Origin(
                data_dir=data_dir,
                dataset_name="flowers",
                which_set="train"
            ),

            batch_size=64,
            shuffle=True,
            num_workers=0
        )

        valid_data_loader = DataLoader(

            Text2ImageDataset_Origin(
                data_dir=data_dir,
                dataset_name="flowers",
                which_set="train"
            ),

            batch_size=64,
            shuffle=False,
            num_workers=0
        )


    else:
        raise AssertionError("dataset_name not valid!")

    start_time = datetime.datetime.now().strftime('%m%d_%H%M%S')
    save_path = os.path.join(args.save_path, start_time)

    trainer = Trainer(gan_type=args.gan_type,
                      train_data_loader=train_data_loader,
                      valid_data_loader=valid_data_loader,
                      num_epochs=args.num_epochs,
                      lr=args.lr,
                      save_path=save_path,
                      l1_coef=args.l1_coef,
                      l2_coef=args.l2_coef,
                      pre_trained_disc=args.pre_trained_disc,
                      pre_trained_gen=args.pre_trained_gen,
                      )

    trainer.train()
