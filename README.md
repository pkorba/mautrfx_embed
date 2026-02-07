# MautrFxEmbed  
A maubot plugin that passively scans your chats for links to X/Twitter, BlueSky, Mastodon posts, Reddit, Lemmy posts or comments, Instagram reels, TikTok videos, and responds with a message that embeds the content of those links. This project was inspired by FxEmbed.

### Key features  
- message contains the full content of the post and the quoted post (if there is any)
- plugin generates thumbnails for all the media that is embedded inside the post
- configurable size of previewed images,
- thumbnails function as links to the original media
- plugin supports the translation syntax from FxEmbed but only for X/Twitter posts
- plugin respects NSFW status of original posts, but it's possible to override this in the settings
- links to videos bring you directly to a barebones media player. No need to deal with clunky Reddit's / Instagram's video players
- for Reddit and Lemmy the plugin supports both post links and comment permalinks

## Screenshots  
<img width="30%" height="30%" alt="twitter_video" src="https://github.com/user-attachments/assets/bc714d3d-85ab-4f79-9ace-9c863b68b4ca" />
<img width="30%" height="30%" alt="twitter" src="https://github.com/user-attachments/assets/23f70929-6343-45c5-bc2a-fe35959fc76e" />
<img width="30%" height="30%" alt="mastodon" src="https://github.com/user-attachments/assets/644140b2-e432-4796-a3d9-8d783372a924" />
<img width="30%" height="30%" alt="bsky" src="https://github.com/user-attachments/assets/214d307a-0e5f-4da6-a1e9-8c58745a08b6" />
<img width="30%" height="30%" alt="twitter_translate" src="https://github.com/user-attachments/assets/9f7dcf9b-94e4-41fd-a1e3-090a59b93306" />
<img width="30%" height="30%" alt="reddit" src="https://github.com/user-attachments/assets/36acdec1-2d64-4fdd-9d34-83b6b771ae1c" />
<img width="30%" height="30%" alt="instagram" src="https://github.com/user-attachments/assets/081ad747-e486-4967-90b4-b5fc10c2bfa9" />

## Usage  
Just paste a link in the chat. The bot will scan the message and if it matches the criteria, it will provide an embed.  

## Configuration  
You can configure the plugin in maubot's control panel.  
* `nitter_redirect` - this setting controls whether the plugin will replace most of X/Twitter links within an embed with links using address defined in `nitter_url` (default: `true`)  
* `nitter_url`: address of a Nitter instance (default: `nitter.net`)  
* `player` - address of a HLS media player that is capable of playing BlueSky/Reddit video links. (default: `https://korba.neocities.org/player?url=`)
* `show_nsfw` - by default plugin respects spoiler status of the post and blurs sensitive media. If you want to override these settings, you can set this pref to `true` (default `false`)
* `thumbnail_large` - maximum thumbnail size in pixels when there's only one image/video in a post/quote
* `thumbnail_small` - maximum thumbnail size in pixels when there's more than one image/video in a post/quote
* `forum_max_length` - maximum length of a Reddit/Lemmy post before its content is hidden in `<details>` disclosure widget. Applies to Reddit, Lemmy, Instagram, and TikTok posts.
* `localtime`  - if `true` uses local time, if `false` uses UTC time zone (default `true`)

Settings contain several whitelists with URLs for each of the supported services. The lists contain original service's addresses but can also contain URLs of alternative privacy frontends like Nitter or Redlib instances. You can freely add new or remove existing URLs from there. There are no lists for Mastodon and Lemmy because there are hundreds of instances of these, and it's impossible to list them all. That's why the plugin tries to recognize these purely based on a regular expression. This may lead to some false positives, but in that case the plugin will just fail silently.

## FAQ  
**Q:** Why BlueSky/Reddit videos open in a website with some suspicious looking URL?  
**A:** BlueSky and Reddit don't provide nice links that can be played in a browser out of the box. For that, you need a HLS player. I couldn't find an existing trustworthy website with such a player for this, so I made my own and put it on my page on neocities.org. If you want, you can host your own player. The player code is included in player.html inside this repository.

**Q:** But why don't you just attach the video to the message instead of doing this mumbo jumbo with custom media player that opens inside a browser?  
**A:** I don't want to download and then reupload the videos to the Matrix server. It would take too much time to generate a message that way. Other than that, file size limits for attachments can differ depending on a Matrix server. It's usually around 100 MiB. So not every video could be uploaded anyway, because file size limits of some social media allow for videos much bigger than that (Twitter videos can be up to 16 GiB in size). It also costs money to host a Matrix server. Storing big blobs of data increases these costs. Many Matrix servers already operate on a shoestring budget. I don't want users of this plugin to accidentally become a burden to some poor Synapse administrator, because there are users who spam chat with Twitter links containing a lot of videos.

**Q:** I don't see media previews in my client!  
**A:** Some clients do not support inline images (`<img>` HTML element) or they have a problem displaying them if the image is a part of a link (`<a>` HTML element). For example, at the time of writing this answer, out of notable clients, Element X Android doesn't support displaying inline images. SchildiChat Next can display them but not when they function as a link to an external URL. 

**Q:** Why is there a list of media in a post if there are previews already?  
**A:** Not all clients can display the previews. See the previous question.

**Q:** Why GIF previews don't autoplay?  
**A:** All supported services display GIFs as MP4 videos and I decided not to embed videos directly in the message for the reasons stated above.

### Data sources:  
- X/Twitter - [FxEmbed API](https://github.com/FxEmbed/FxEmbed)
- Bluesky - [Bluesky API](https://docs.bsky.app/docs/api/app-bsky-feed-get-post-thread)
- Mastodon - [Mastodon API](https://docs.joinmastodon.org/methods/statuses/#get)
- Instagram - kkinstagram/Instagram website
- TikTok - TikTok website
- Reddit - [Reddit API](https://old.reddit.com/dev/api#GET_api_info)
- Lemmy - [Lemmy API](https://join-lemmy.org/api/main#tag/Post/operation/GetPost)

### Known issues  
- If you put a URL inside a spoiler, bot still generates an unobscured message. This is unlikely to get fixed because obscuring the bot's whole message works correctly only in Element Web/Desktop.

## Disclaimer  
This plugin is not affiliated with X/Twitter, Bluesky, Mastodon, Instagram, TikTok, Reddit, Lemmy, FxEmbed, and kkinstagram. It is not intended for commercial use or any purpose that violates Terms of Service of mentioned services. By using this plugin, you acknowledge that you will not use it in a way that infringes on these service's terms.
