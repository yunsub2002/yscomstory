// node gen_cli.js <seed> → 새 괴담 원고를 표준출력으로
const fs = require('fs'), vm = require('vm'), ctx = {}; vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname + '/gen.js', 'utf8') + ';this.genStory = genStory;', ctx);
process.stdout.write(ctx.genStory(+process.argv[2] || Date.now()));
