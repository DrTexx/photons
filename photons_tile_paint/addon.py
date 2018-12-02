from photons_app.actions import an_action

from option_merge_addons import option_merge_addon_hook
from input_algorithms.meta import Meta

__shortdesc__ = "Utilities for painting on the tiles"

@option_merge_addon_hook(extras=[
      ("lifx.photons", "messages")
    , ("lifx.photons", "themes")
    , ("lifx.photons", "products_registry")
    ])
def __lifx__(*args, **kwargs):
    pass

class Animator:
    def __init__(self, animationkls, optionskls, __doc__):
        self.__doc__ = __doc__
        self.optionskls = optionskls
        self.animationkls = animationkls

    async def animate(self, target, afr, reference, options):
        options = self.optionskls.FieldSpec().normalise(Meta.empty(), options)
        return await self.animationkls(target, afr, options).animate(reference)

    def __set_name__(self, owner, name):
        self.name = name

    def make_action(self):
        async def action(collector, target, reference, **kwargs):
            extra = collector.configuration["photons_app"].extra_as_json
            async with target.session() as afr:
                await self.animate(target, afr, reference, extra)

        action.__name__ = self.name
        action.__doc__ = self.__doc__

        return an_action(needs_target=True, special_reference=True)(action)

from photons_tile_paint.time.animation import TileTimeAnimation
from photons_tile_paint.time.options import TileTimeOptions

from photons_tile_paint.marquee.animation import TileMarqueeAnimation
from photons_tile_paint.marquee.options import TileMarqueeOptions

from photons_tile_paint.pacman.animation import TilePacmanAnimation
from photons_tile_paint.pacman.options import TilePacmanOptions

from photons_tile_paint.nyan import TileNyanAnimation
from photons_tile_paint.nyan import TileNyanOptions

from photons_tile_paint.gameoflife.animation import TileGameOfLifeAnimation
from photons_tile_paint.gameoflife.options import TileGameOfLifeOptions

from photons_tile_paint.twinkles import TileTwinklesAnimation
from photons_tile_paint.twinkles import TileTwinklesOptions

class Animations:
    tile_time = Animator(TileTimeAnimation, TileTimeOptions
        , """
          Print time to the tiles

          ``lifx lan:tile_time <reference>``
          """
        )

    tile_marquee = Animator(TileMarqueeAnimation, TileMarqueeOptions
        , """
          Print scrolling text to the tiles

          ``lifx lan:tile_marquee <reference> -- '{"text": "hello there"}'``
          """
        )

    tile_pacman = Animator(TilePacmanAnimation, TilePacmanOptions
        , """
          Make pacman go back and forth across your tiles

          ``lifx lan:tile_pacman <reference>``
          """
        )

    tile_nyan = Animator(TileNyanAnimation, TileNyanOptions
        , """
          Make nyan go back and forth across your tiles

          ``lifx lan:tile_nyan <reference>``
          """
        )

    tile_gameoflife = Animator(TileGameOfLifeAnimation, TileGameOfLifeOptions
        , """
          Run a Conway's game of life simulation on the tiles

          ``lifx lan:tile_gameoflife <reference>``
          """
        )

    tile_twinkles = Animator(TileTwinklesAnimation, TileTwinklesOptions
        , """
          Random twinkles on the tiles
          """
        )

for attr in dir(Animations):
    if attr.startswith("tile_"):
        locals()[attr] = getattr(Animations, attr).make_action()

if __name__ == "__main__":
    from photons_app.executor import main
    import sys
    main(["lan:tile_twinkles"] + sys.argv[1:])
