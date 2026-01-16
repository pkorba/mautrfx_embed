# MautrFxEmbed  
A maubot plugin that passively scans your chats for links to X/Twitter, BlueSky, Mastodon posts, Instagram reels and responds with a message that embeds the content of said links. This project was inspired by FxEmbed.

### Key features  
- message contains the full content of the post and the quoted post (if there is any)
- plugin generates thumbnails for all the media that is embedded inside the post
- thumbnails function as links to the original media
- plugin supports the translation syntax from FxEmbed but only for X/Twitter posts

## Usage  
Just paste a link in the chat. The bot will scan the message and if it matches the criteria, it will provide an embed.  

## Configuration  
You can configure the plugin in maubot's control panel.  
* `nitter_redirect` - this setting controls whether plugin will replace most of X/Twitter links within an embed with links using address defined in `nitter_url` (default: `true`)  
* `nitter_url`: address of a Nitter instance (default: `nitter.net`)  
* `bsky_player` - address of a HLS media player that is capable of playing BlueSky video links. (default: `https://korba.neocities.org/player?url=`)

## Plugin data sources:
- X/Twitter - [FxEmbed API](https://github.com/FxEmbed/FxEmbed)
- Bluesky - [Bluesky API](https://docs.bsky.app/docs/api/app-bsky-feed-get-post-thread)
- Mastodon - [Mastodon API](https://docs.joinmastodon.org/methods/statuses/#get)
- Instagram - Plugin fetches the URL to the reel from kkinstagram.com

## Known issues  
- Missing support for custom emojis on Mastodon

## Planned features  
- Reddit support
- Lemmy support
- Piefed support

## FAQ  
**Q:** Why BlueSky videos open in a website with some suspicious looking URL?  
**A:** BlueSky doesn't provide nice links that can be played in a browser out of the box. For that, you need a HLS player. I couldn't find an existing trustworthy website with such a player for this, so I made my own and put it on my page on neocities.org. If you want, you can host your own player. The player code is included in player.html inside this repository.

**Q:** But why don't you just attach the video to the message instead of doing this mumbo jumbo with custom media player that opens inside a browser?  
**A:** File size limit can differ depending on a Matrix server. It's usually around 100 MiB. It also costs money to host a Matrix server. Storing big blobs of data increases these costs. I don't control file size limits on social media. Twitter videos can be up to 16 GiB in size. I am not uploading that anywhere and becoming a burden to some poor Synapse administrator because someone spammed a chat with Twitter links. You can play your videos in a browser.  

**Q:** I don't see media previews in my client!  
**A:** Some clients do not support inline images (`<img>` HTML element) or they have a problem displaying them if the image is a part of a link (`<a>` HTML element). For example, at the time of writing this answer, out of notable clients, Element X Android doesn't support displaying inline images. SchildiChat Next can display them but not when they function as a link to an external URL. 

**Q:** Why is there a list of media in a post if there are previews already?  
**A:** Not all clients can display the previews. See the previous question.

**Q:** Why GIF previews don't autoplay?  
**A:** All supported services display GIFs as MP4 videos and I can't embed a video directly in the message.

## Disclaimer  
This plugin is not affiliated with X/Twitter, Bluesky, Mastodon, Instagram, FxEmbed, and kkinstagram. It is not intended for commercial use or any purpose that violates Terms of Service of mentioned services. By using this plugin, you acknowledge that you will not use it in a way that infringes on these service's terms.
