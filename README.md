# style_trasnfer_lyric
Style transfer in music - A lyrical approach

Song lyrics are a source of rich structural and lin- guistic information in music but have not been ex- plored extensively in NLP. We believe that with re- cent advancements in AI especially in the field of NLP, we have the ability to transfer styles of text from one genre(domain) to another. Exploring this technique in song lyrics presents an interesting problem because of an inherent style/rhyme as well as content representation manifested in different genres. This translates to a style transfer task with non parallel corpora in NLP. 

For our work, we have chosen rap and country music genre because they are quite distinct in terms of style. We composed a lyric dataset of 12000 songs labeled by genre (rap and country music) and comprehensive phonetic transcriptions of words especially unique to rap music. We have improved our simple auto-encoder baseline model by training a shared encoder - multi-decoder with adversarial learning which basically has two decoders for the two different genres. We evaluated our models on metrics like semantic score, classification score and introduced two novel metrics called uniqueness score and rhyme score to better capture a sense of content preservation and style transfer.

The details of project and our results can be found [here](https://docs.google.com/presentation/d/1qPNv8ShZ3cdzkwbZVIfuW5GWAZeNzsfsvF2yTgUHR3g/edit?usp=sharing)

The repo does **not** include our dataset because we have not yet decided on the best strategy to release it. However, it contains the scripts we use to scrap and parse song lyrics from the web.

#Crawling data for a specific genre by artist
`pylrics3` can be used to fetch lyrics by artist.
Configuration variables before use:
In the `__init__` method set `self.artists` to the list of artists you want to get the lyrics for and set `self.artist_idx` to 0 or a specific index of the `self.artists` list. The script would start downloading lyrics from that artist
Add database connection params in the `self._conn = psycopg2.connect` block in `__init__` method.
