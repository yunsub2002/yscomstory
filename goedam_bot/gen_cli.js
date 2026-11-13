// node gen_cli.js <seed>                          → 짧은 괴담 1편 (예전 방식)
// node gen_cli.js <seed> episode [분] [피할무대,..] → 20~30분 괴담 모음 원고
// node gen_cli.js <seed> short <무대>              → 숏츠용 3분 이하 한 편
const fs = require('fs'), vm = require('vm'), ctx = {}; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname + '/gen.js', 'utf8') + '\n' + fs.readFileSync(__dirname + '/gen_long.js', 'utf8') +
  ';this.genStory = genStory; this.genEpisode = genEpisode; this.genShort = genShort;', ctx);
const [seed, mode, a, b] = process.argv.slice(2), sd = +seed || Date.now();
if (mode === 'episode') process.stdout.write(ctx.genEpisode(sd, { minutes: +a || 25, avoid: (b || '').split(',').filter(Boolean) }));
else if (mode === 'short') process.stdout.write(ctx.genShort(sd, a || ''));
else process.stdout.write(ctx.genStory(sd));
