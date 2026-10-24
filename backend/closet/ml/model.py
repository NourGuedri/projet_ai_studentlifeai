"""Architecture du réseau : EfficientNet-B0 + 3 têtes (type, couleur, style)."""
import torch
import torch.nn as nn
from torchvision import models

IMG_SIZE = 224
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]


class ClothingNet(nn.Module):
    def __init__(self, n_article, n_color, n_style, pretrained=True):
        super().__init__()
        weights = models.EfficientNet_B0_Weights.DEFAULT if pretrained else None
        backbone = models.efficientnet_b0(weights=weights)
        self.features, self.pool = backbone.features, backbone.avgpool
        self.drop = nn.Dropout(0.3)
        self.h_article = nn.Linear(1280, n_article)
        self.h_color = nn.Linear(1280, n_color)
        self.h_style = nn.Linear(1280, n_style)

    def forward(self, x):
        z = self.drop(torch.flatten(self.pool(self.features(x)), 1))
        return self.h_article(z), self.h_color(z), self.h_style(z)
