# frozen_string_literal: true

require "open3"
require "json"
require "tmpdir"

RSpec.describe Jfin2etv::Runner do
  let(:lib_dir) { File.expand_path("../lib", __dir__) }

  def write_script(dir, name, body)
    path = File.join(dir, name)
    File.write(path, body)
    path
  end

  def run_ruby(scripts, env: {})
    cmd = [
      "ruby",
      "-I", lib_dir,
      "-r", "jfin2etv/runner",
      "-e",
      "Jfin2etv::Runner.run(#{scripts.inspect}, channel: 'test')",
    ]
    Open3.capture3(env, *cmd)
  end

  it "exits 0 and emits JSON for a valid script batch" do
    Dir.mktmpdir do |dir|
      script = write_script(dir, "main.rb", <<~RB)
        channel number: "01", name: "Test"
        collection :c, "library:\\"X\\" AND type:movie", mode: :shuffle
        filler :fallback, local: "/media/x.mkv"
        layout :l do
          main
          fill with: :fallback
        end
        schedule do
          block at: "00:00", collection: :c, layout: :l
        end
      RB

      stdout, stderr, status = run_ruby([script])
      expect(status.exitstatus).to eq(0), "stderr=#{stderr}"
      ast = JSON.parse(stdout)
      expect(ast["channel"]["number"]).to eq "01"
    end
  end

  it "exits 2 on a DSL error" do
    Dir.mktmpdir do |dir|
      script = write_script(dir, "main.rb", <<~RB)
        channel number: "01", name: "Test"
        schedule do
          block at: "99:99", collection: :c, layout: :l
        end
      RB
      _stdout, stderr, status = run_ruby([script])
      expect(status.exitstatus).to eq 2
      expect(stderr).to match(/DSL error/)
    end
  end

  it "exits 1 on an uncaught exception" do
    Dir.mktmpdir do |dir|
      script = write_script(dir, "main.rb", "raise 'boom'")
      _stdout, _stderr, status = run_ruby([script])
      expect(status.exitstatus).to eq 1
    end
  end

  it "honors VALIDATE_ONLY=1 (no stdout JSON)" do
    Dir.mktmpdir do |dir|
      script = write_script(dir, "main.rb", <<~RB)
        channel number: "01", name: "Test"
        collection :c, "library:\\"X\\" AND type:movie", mode: :shuffle
        filler :fallback, local: "/media/x.mkv"
        layout :l do
          main
          fill with: :fallback
        end
        schedule do
          block at: "00:00", collection: :c, layout: :l
        end
      RB
      stdout, _stderr, status = run_ruby([script], env: { "VALIDATE_ONLY" => "1" })
      expect(status.exitstatus).to eq 0
      expect(stdout.strip).to eq ""
    end
  end
end
