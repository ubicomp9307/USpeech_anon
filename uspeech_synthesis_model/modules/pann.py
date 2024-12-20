import torch
import torch.nn as nn
import torch.nn.functional as F


def interpolate(x, ratio):
    """Interpolate data in time domain. This is used to compensate the
    resolution reduction in downsampling of a CNN.
    Args:
      x: (batch_size, time_steps, classes_num)
      ratio: int, ratio to interpolate
    Returns:
      upsampled: (batch_size, time_steps * ratio, classes_num)
    """
    (batch_size, time_steps, classes_num) = x.shape
    upsampled = x[:, :, None, :].repeat(1, 1, ratio, 1)
    upsampled = upsampled.reshape(batch_size, time_steps * ratio, classes_num)
    return upsampled


def init_bn(bn):
    """Initialize a Batchnorm layer. """
    bn.bias.data.fill_(0.)
    bn.weight.data.fill_(1.)


def init_layer(layer):
    """Initialize a Linear or Convolutional layer. """
    nn.init.xavier_uniform_(layer.weight)

    if hasattr(layer, 'bias'):
        if layer.bias is not None:
            layer.bias.data.fill_(0.)


class ConvBlock(nn.Module):
    def __init__(self, in_channels, out_channels):

        super(ConvBlock, self).__init__()

        self.conv1 = nn.Conv2d(in_channels=in_channels,
                              out_channels=out_channels,
                              kernel_size=(3, 3), stride=(1, 1),
                              padding=(1, 1), bias=False)

        self.conv2 = nn.Conv2d(in_channels=out_channels,
                              out_channels=out_channels,
                              kernel_size=(3, 3), stride=(1, 1),
                              padding=(1, 1), bias=False)

        self.bn1 = nn.BatchNorm2d(out_channels)
        self.bn2 = nn.BatchNorm2d(out_channels)

        self.init_weight()

    def init_weight(self):
        init_layer(self.conv1)
        init_layer(self.conv2)
        init_bn(self.bn1)
        init_bn(self.bn2)


    def forward(self, input, pool_size=(2, 2), pool_type='avg'):

        x = input
        x = F.relu_(self.bn1(self.conv1(x)))
        x = F.relu_(self.bn2(self.conv2(x)))
        if pool_type == 'max':
            x = F.max_pool2d(x, kernel_size=pool_size)
        elif pool_type == 'avg':
            x = F.avg_pool2d(x, kernel_size=pool_size)
        elif pool_type == 'avg+max':
            x1 = F.avg_pool2d(x, kernel_size=pool_size)
            x2 = F.max_pool2d(x, kernel_size=pool_size)
            x = x1 + x2
        else:
            raise Exception('Incorrect argument!')

        return x


class Cnn14(nn.Module):
    def __init__(self, embed_dim, enable_fusion=False, fusion_type='None', pretrained=False):
        super(Cnn14, self).__init__()

        self.enable_fusion = enable_fusion
        self.fusion_type = fusion_type
        self.pretrained = pretrained
        

        self.bn = nn.BatchNorm2d(128)

        if (self.enable_fusion) and (self.fusion_type == 'channel_map'):
            self.conv_block1 = ConvBlock(in_channels=4, out_channels=64)
        else:
            self.conv_block1 = ConvBlock(in_channels=1, out_channels=64)
        self.conv_block2 = ConvBlock(in_channels=64, out_channels=128)
        self.conv_block3 = ConvBlock(in_channels=128, out_channels=256)
        self.conv_block4 = ConvBlock(in_channels=256, out_channels=512)
        self.conv_block5 = ConvBlock(in_channels=512, out_channels=1024)
        self.conv_block6 = ConvBlock(in_channels=1024, out_channels=2048)

        self.fc1 = nn.Linear(2048, 2048, bias=True)
        self.final_project = nn.Linear(2048, embed_dim, bias=True)

        self.init_weight()

    def init_weight(self):
        init_bn(self.bn)
        init_layer(self.fc1)
        init_layer(self.final_project)

    def forward(self, input, mixup_lambda=None, device=None):
        """
        Input: (batch_size, data_length)"""

        x = input
        x = x.transpose(1, 3)
        x = self.bn(x)
        x = x.transpose(1, 3)

        x = self.conv_block1(x, pool_size=(2, 2), pool_type='avg')
        x = F.dropout(x, p=0.2, training=self.training)
        x = self.conv_block2(x, pool_size=(2, 2), pool_type='avg')
        # if we need the audio temporal steps to be 29, we need to change the pool_size to (1, 1)
        # from block 3 to block 6
        x = F.dropout(x, p=0.2, training=self.training)
        x = self.conv_block3(x, pool_size=(1, 1), pool_type='avg')
        x = F.dropout(x, p=0.2, training=self.training)
        x = self.conv_block4(x, pool_size=(1, 1), pool_type='avg')
        x = F.dropout(x, p=0.2, training=self.training)
        x = self.conv_block5(x, pool_size=(1, 1), pool_type='avg')
        x = F.dropout(x, p=0.2, training=self.training)
        x = self.conv_block6(x, pool_size=(1, 1), pool_type='avg')
        x = F.dropout(x, p=0.2, training=self.training)
        x = torch.mean(x, dim=3)

        latent_x1 = F.max_pool1d(x, kernel_size=3, stride=1, padding=1)
        latent_x2 = F.avg_pool1d(x, kernel_size=3, stride=1, padding=1)
        latent_x = latent_x1 + latent_x2
        latent_x = latent_x.transpose(1, 2)
        latent_x = F.relu_(self.fc1(latent_x))
        x = F.relu_(self.fc1(latent_x))
        output = self.final_project(x)
        return output

class Cnn14_unet(nn.Module):
    def __init__(self, embed_dim, enable_fusion=False, fusion_type='None', pretrained=False):
        super(Cnn14_unet, self).__init__()

        self.enable_fusion = enable_fusion
        self.fusion_type = fusion_type
        self.pretrained = pretrained
        

        self.bn = nn.BatchNorm2d(128)

        if (self.enable_fusion) and (self.fusion_type == 'channel_map'):
            self.conv_block1 = ConvBlock(in_channels=4, out_channels=64)
        else:
            self.conv_block1 = ConvBlock(in_channels=1, out_channels=64)
        self.conv_block2 = ConvBlock(in_channels=64, out_channels=128)
        self.conv_block3 = ConvBlock(in_channels=128, out_channels=256)
        self.conv_block4 = ConvBlock(in_channels=256, out_channels=512)
        self.conv_block5 = ConvBlock(in_channels=512, out_channels=1024)
        self.conv_block6 = ConvBlock(in_channels=1024, out_channels=2048)

        self.fc1 = nn.Linear(2048, 2048, bias=True)
        self.final_project = nn.Linear(2048, embed_dim, bias=True)

        self.init_weight()

    def init_weight(self):
        init_bn(self.bn)
        init_layer(self.fc1)
        init_layer(self.final_project)

    def forward(self, input, mixup_lambda=None, device=None):
        """
        Input: (batch_size, data_length)
        """
        encoder_features = []

        x = input
        x = x.transpose(1, 3)
        x = self.bn(x)
        x = x.transpose(1, 3)

        x = self.conv_block1(x, pool_size=(2, 2), pool_type='avg')
        encoder_features.append(x)
        x = F.dropout(x, p=0.2, training=self.training)

        x = self.conv_block2(x, pool_size=(2, 2), pool_type='avg')
        # if we need the audio temporal steps to be 29, we need to change the pool_size to (1, 1)
        # from block 3 to block 6
        encoder_features.append(x)
        x = F.dropout(x, p=0.2, training=self.training)

        x = self.conv_block3(x, pool_size=(1, 1), pool_type='avg')
        encoder_features.append(x)
        x = F.dropout(x, p=0.2, training=self.training)

        x = self.conv_block4(x, pool_size=(1, 1), pool_type='avg')
        encoder_features.append(x)
        x = F.dropout(x, p=0.2, training=self.training)

        x = self.conv_block5(x, pool_size=(1, 1), pool_type='avg')
        encoder_features.append(x)
        x = F.dropout(x, p=0.2, training=self.training)

        x = self.conv_block6(x, pool_size=(1, 1), pool_type='avg')
        encoder_features.append(x)
        x = F.dropout(x, p=0.2, training=self.training)

        x = torch.mean(x, dim=3)

        latent_x1 = F.max_pool1d(x, kernel_size=3, stride=1, padding=1)
        latent_x2 = F.avg_pool1d(x, kernel_size=3, stride=1, padding=1)
        latent_x = latent_x1 + latent_x2
        latent_x = latent_x.transpose(1, 2)
        latent_x = F.relu_(self.fc1(latent_x))
        x = F.relu_(self.fc1(latent_x))
        # print(x.shape)
        output = self.final_project(x)
        # print(output.shape)

        return output, encoder_features